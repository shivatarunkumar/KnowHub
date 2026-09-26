"""BigQuery as the application database.

What the services use instead of an SQLAlchemy session:

    db = get_db()
    user = await db.row("SELECT * FROM {users} WHERE email = @email", email=email)
    batch = db.batch()
    batch.insert("refresh_tokens", {...})
    batch.update("users", {"id": user.id}, {"last_login_at": now})
    await batch.commit()          # the writes, in parallel per table

- `{users}` names a table; it becomes `project.dataset.users`. Anything else in braces is
  an error, so a typo fails loudly instead of querying the wrong thing.
- `@name` is a query parameter, typed from the Python value. Writes built by insert() and
  update() are typed from the table's schema in infra/gcs/bq/tables, so NULLs and JSON
  columns get the right type without the caller saying so.
- UUIDs are STRING columns; they come back as uuid.UUID (any column named id, *_id,
  replaced_by, added_by, created_by), so comparisons with path parameters just work.
- Writes go through DML, never the streaming API: streamed rows cannot be updated or
  deleted for ~30 minutes, and every table here is updated.

BigQuery does not enforce keys and allows only a few concurrent mutations per table.
commit() retries the "concurrent update" aborts that causes; uniqueness is enforced by
the services (see project-bq.md).
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time
import uuid
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from google.api_core import exceptions as gexc
from google.cloud import bigquery

from app.core.config import Settings, get_settings

log = logging.getLogger("knowhub.bq")

TABLES_DIR = Path(__file__).resolve().parents[3] / "infra" / "gcs" / "bq" / "tables"
SQL_PREVIEW = 160
SLOW_MS = 3000  # a BigQuery round trip is ~0.3-1s; only log at INFO when it is unusually slow
RETRIES = 5
RETRYABLE = ("concurrent update", "could not serialize access", "transaction is aborted")

TABLE_RE = re.compile(r"\{(\w+)\}")
UUID_COLUMNS = {"replaced_by", "added_by", "created_by"}
NOT_UUID = {"session_id", "message_id", "request_id"}


class BigQueryError(Exception):
    """A query failed for a reason that retrying will not fix."""


# ------------------------------------------------------------------ rows
class Row(dict):
    """A result row: a dict you can also read as attributes (user.handle)."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


def is_uuid_column(name: str) -> bool:
    if name in NOT_UUID:
        return False
    return name == "id" or name.endswith("_id") or name in UUID_COLUMNS


def _from_bq(name: str, value: Any) -> Any:
    if isinstance(value, str) and is_uuid_column(name):
        try:
            return uuid.UUID(value)
        except ValueError:
            return value
    return value


# ------------------------------------------------------------------ schema
@lru_cache
def schema() -> dict[str, dict[str, dict]]:
    """{table: {column: field}} from infra/gcs/bq/tables/*.json, the same files Terraform uses."""
    tables: dict[str, dict[str, dict]] = {}
    for path in sorted(TABLES_DIR.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        tables[path.stem] = {field["name"]: field for field in spec["schema"]}
    if not tables:
        raise BigQueryError(f"no table definitions found in {TABLES_DIR}")
    return tables


# ------------------------------------------------------------------ parameters
class Typed:
    """A value with an explicit BigQuery type: needed for NULL, which has no type of its own."""

    __slots__ = ("type", "value")

    def __init__(self, value: Any, type_: str) -> None:
        self.value = value
        self.type = type_


def null(type_: str = "STRING") -> Typed:
    return Typed(None, type_)


def _plain(value: Any) -> Any:
    return str(value) if isinstance(value, uuid.UUID) else value


def _scalar_type(value: Any) -> str:
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT64"
    if isinstance(value, float):
        return "FLOAT64"
    if isinstance(value, datetime):
        return "TIMESTAMP"
    if isinstance(value, date):
        return "DATE"
    return "STRING"


def make_param(name: str, value: Any) -> bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter:
    if isinstance(value, Typed):
        if value.type.startswith("ARRAY<"):
            element = value.type[6:-1]
            return bigquery.ArrayQueryParameter(name, element, [_plain(v) for v in value.value or []])
        return bigquery.ScalarQueryParameter(name, value.type, _plain(value.value))
    if isinstance(value, list | tuple | set | frozenset):
        items = [_plain(v) for v in value]
        element = _scalar_type(items[0]) if items else "STRING"
        return bigquery.ArrayQueryParameter(name, element, items)
    if value is None:
        return bigquery.ScalarQueryParameter(name, "STRING", None)
    return bigquery.ScalarQueryParameter(name, _scalar_type(value), _plain(value))


def column_value(table: str, column: str, value: Any) -> tuple[str, Any]:
    """(SQL expression, parameter value) for writing `value` into table.column."""
    if isinstance(value, Typed):
        return "{}", value  # the caller already chose the type
    try:
        field = schema()[table][column]
    except KeyError:
        raise BigQueryError(f"{table}.{column} is not in infra/gcs/bq/tables/{table}.json") from None
    type_ = field["type"]
    if field.get("mode") == "REPEATED":
        return "{}", Typed(list(value or []), f"ARRAY<{type_}>")
    if type_ == "JSON":
        # NULL becomes {} like the Postgres default: the column is NOT NULL in both
        return "PARSE_JSON({})", Typed(json.dumps(value if value is not None else {}, default=str), "STRING")
    return "{}", Typed(_plain(value), type_)


# ------------------------------------------------------------------ statements
class Statement:
    """One SQL statement, its parameters, and the table it writes (if any)."""

    def __init__(self, sql: str, params: dict[str, Any] | None = None, *, table: str | None = None) -> None:
        self.sql = sql
        self.params = params or {}
        self.table = table if table is not None else written_table(sql)


WRITE_RE = re.compile(r"^\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE)\s+\{(\w+)\}", re.I)


def written_table(sql: str) -> str | None:
    """The table a DML statement changes: INSERT INTO {t}, UPDATE {t}, DELETE FROM {t}, MERGE {t}."""
    match = WRITE_RE.match(sql)
    return match.group(1) if match else None


def insert_statement(table: str, rows: Sequence[dict[str, Any]]) -> Statement:
    columns: list[str] = []
    for row in rows:
        columns.extend(c for c in row if c not in columns)
    params: dict[str, Any] = {}
    tuples = []
    fields = schema().get(table, {})
    for index, row in enumerate(rows):
        values = []
        for column in columns:
            if column not in row and "defaultValueExpression" in fields.get(column, {}):
                values.append("DEFAULT")  # another row in this INSERT set it; this one takes the default
                continue
            expression, value = column_value(table, column, row.get(column))
            name = f"r{index}_{column}"
            params[name] = value
            values.append(expression.format(f"@{name}"))
        tuples.append(f"({', '.join(values)})")
    sql = f"INSERT INTO {{{table}}} ({', '.join(columns)}) VALUES {', '.join(tuples)}"
    return Statement(sql, params, table=table)


def where_clause(table: str, where: dict[str, Any], prefix: str = "w_") -> tuple[str, dict[str, Any]]:
    parts, params = [], {}
    for column, value in where.items():
        name = f"{prefix}{column}"
        if value is None:
            parts.append(f"{column} IS NULL")
            continue
        if isinstance(value, list | tuple | set | frozenset):
            parts.append(f"{column} IN UNNEST(@{name})")
            params[name] = [_plain(v) for v in value]
            continue
        _, typed = column_value(table, column, value)
        parts.append(f"{column} = @{name}")
        params[name] = typed
    if not parts:
        raise BigQueryError(f"refusing to write every row of {table}: no WHERE condition")
    return " AND ".join(parts), params


NOW = Typed(None, "CURRENT_TIMESTAMP")  # update(..., {"revoked_at": NOW}): the server's clock


def update_statement(table: str, where: dict[str, Any], values: dict[str, Any]) -> Statement:
    values = dict(values)
    if "updated_at" in schema()[table] and "updated_at" not in values:
        values["updated_at"] = NOW  # what the Postgres trigger did
    sets, params = [], {}
    for column, value in values.items():
        if value is NOW:
            sets.append(f"{column} = CURRENT_TIMESTAMP()")
            continue
        expression, typed = column_value(table, column, value)
        sets.append(f"{column} = {expression.format(f'@s_{column}')}")
        params[f"s_{column}"] = typed
    condition, where_params = where_clause(table, where)
    return Statement(
        f"UPDATE {{{table}}} SET {', '.join(sets)} WHERE {condition}", {**params, **where_params}, table=table
    )


def delete_statement(table: str, where: dict[str, Any]) -> Statement:
    condition, params = where_clause(table, where)
    return Statement(f"DELETE FROM {{{table}}} WHERE {condition}", params, table=table)


# ------------------------------------------------------------------ database
class BigQueryDB:
    def __init__(self, settings: Settings) -> None:
        self.project = settings.bq_db_project_id
        self.dataset = settings.bq_db_dataset
        self.location = settings.bq_db_location
        self._client: bigquery.Client | None = None

    @property
    def client(self) -> bigquery.Client:
        if self._client is None:
            # JOB_CREATION_OPTIONAL: short reads skip creating a job, which is most of
            # BigQuery's per-query latency. DML and scripts still create one.
            self._client = bigquery.Client(
                project=self.project,
                location=self.location,
                default_job_creation_mode="JOB_CREATION_OPTIONAL",
            )
        return self._client

    def table(self, name: str) -> str:
        return f"`{self.project}.{self.dataset}.{name}`"

    def expand(self, sql: str) -> str:
        """{users} → `project.dataset.users`; an unknown name is an error, not a typo that runs."""

        def replace(match: re.Match) -> str:
            name = match.group(1)
            if name not in schema():
                raise BigQueryError(f"unknown table {{{name}}} in query")
            return self.table(name)

        return TABLE_RE.sub(replace, sql)

    # -------------------------------------------------------------- running
    def _run_sync(self, sql: str, params: dict[str, Any]) -> tuple[list[Row], int]:
        text = self.expand(sql)
        config = bigquery.QueryJobConfig(query_parameters=[make_param(k, v) for k, v in params.items()])
        for attempt in range(1, RETRIES + 1):
            started = time.perf_counter()
            try:
                result = self.client.query_and_wait(text, job_config=config)
                rows = [Row({k: _from_bq(k, v) for k, v in row.items()}) for row in result]
            except (gexc.BadRequest, gexc.Conflict, gexc.Forbidden) as exc:
                message = str(exc).lower()
                if attempt < RETRIES and any(marker in message for marker in RETRYABLE):
                    pause = 0.2 * 2 ** (attempt - 1) + random.random() * 0.2
                    log.info(
                        "  bq concurrent-update conflict, retry %d/%d in %.1fs", attempt, RETRIES - 1, pause
                    )
                    time.sleep(pause)
                    continue
                log.warning("bq query failed: %s | %s", exc, _preview(text))
                raise BigQueryError(str(exc)) from exc
            elapsed = (time.perf_counter() - started) * 1000
            affected = getattr(result, "num_dml_affected_rows", None) or 0
            scanned = getattr(result, "total_bytes_processed", None)
            level = logging.INFO if elapsed >= SLOW_MS else logging.DEBUG
            if log.isEnabledFor(level):
                detail = f" rows={len(rows)}" if rows else (f" affected={affected}" if affected else "")
                if scanned:
                    detail += f" scanned={scanned / 1024:.0f}KB"
                log.log(level, "  bq %.0fms%s  %s", elapsed, detail, _preview(text))
            return rows, affected
        raise BigQueryError("gave up after repeated concurrent-update conflicts")  # pragma: no cover

    async def run(self, sql: str, **params: Any) -> tuple[list[Row], int]:
        return await asyncio.to_thread(self._run_sync, sql, params)

    async def rows(self, sql: str, **params: Any) -> list[Row]:
        return (await self.run(sql, **params))[0]

    async def row(self, sql: str, **params: Any) -> Row | None:
        found = await self.rows(sql, **params)
        return found[0] if found else None

    async def scalar(self, sql: str, **params: Any) -> Any:
        found = await self.row(sql, **params)
        return next(iter(found.values())) if found else None

    async def execute(self, sql: str, **params: Any) -> int:
        """Run DML; returns the number of rows it changed."""
        return (await self.run(sql, **params))[1]

    async def insert(self, table: str, *rows: dict[str, Any]) -> None:
        statement = insert_statement(table, rows)
        await self.run(statement.sql, **statement.params)

    async def update(self, table: str, where: dict[str, Any], values: dict[str, Any]) -> int:
        statement = update_statement(table, where, values)
        return await self.execute(statement.sql, **statement.params)

    async def delete(self, table: str, where: dict[str, Any]) -> int:
        statement = delete_statement(table, where)
        return await self.execute(statement.sql, **statement.params)

    def batch(self) -> Batch:
        return Batch(self)


class Batch:
    """Writes collected during a request and sent together, like a session commit.

    - Consecutive inserts into the same table become one multi-row INSERT.
    - Statements on the same table run in the order they were added (delete the old
      links, then insert the new ones); different tables run in parallel.

    Not a transaction, on purpose: a BigQuery multi-statement transaction costs 5-6s
    however small it is, which would make every sign-in take that long. Each statement
    is atomic on its own, and nothing here depends on two tables changing together
    (there are no foreign keys to violate). See project-bq.md.
    """

    def __init__(self, db: BigQueryDB) -> None:
        self.db = db
        self._entries: list[tuple[str, Any]] = []  # ("row", (table, row)) | ("sql", Statement)

    def __len__(self) -> int:
        return len(self._entries)

    def insert(self, table: str, row: dict[str, Any]) -> None:
        """The row is read at commit(), so later changes to the same dict are included."""
        self._entries.append(("row", (table, row)))

    def update(self, table: str, where: dict[str, Any], values: dict[str, Any]) -> None:
        self._entries.append(("sql", update_statement(table, where, values)))

    def delete(self, table: str, where: dict[str, Any]) -> None:
        self._entries.append(("sql", delete_statement(table, where)))

    def execute(self, sql: str, **params: Any) -> None:
        statement = Statement(sql, params)
        if statement.table is None:
            raise BigQueryError("Batch.execute is for INSERT/UPDATE/DELETE/MERGE on a {table}")
        self._entries.append(("sql", statement))

    def compiled(self) -> list[Statement]:
        out: list[Statement] = []
        rows: list[dict[str, Any]] = []
        rows_table: str | None = None
        for kind, entry in self._entries:
            if kind == "row" and entry[0] == rows_table:
                rows.append(entry[1])
                continue
            if rows_table is not None:
                out.append(insert_statement(rows_table, rows))
                rows, rows_table = [], None
            if kind == "row":
                rows_table, rows = entry[0], [entry[1]]
            else:
                out.append(entry)
        if rows_table is not None:
            out.append(insert_statement(rows_table, rows))
        return out

    def chains(self) -> list[list[Statement]]:
        """One ordered chain of statements per table."""
        by_table: dict[str, list[Statement]] = {}
        for statement in self.compiled():
            by_table.setdefault(statement.table or "", []).append(statement)
        return list(by_table.values())

    async def commit(self) -> None:
        chains = self.chains()
        self._entries = []

        async def run_chain(chain: list[Statement]) -> None:
            for statement in chain:
                await self.db.run(statement.sql, **statement.params)

        await asyncio.gather(*(run_chain(chain) for chain in chains))


def _preview(sql: str) -> str:
    flat = " ".join(sql.split())
    return f"{flat[:SQL_PREVIEW]}…" if len(flat) > SQL_PREVIEW else flat


@lru_cache
def get_db() -> BigQueryDB:
    return BigQueryDB(get_settings())


def uuids(values: Iterable[Any]) -> list[str]:
    """For `IN UNNEST(@ids)`: UUIDs travel as strings."""
    return [str(v) for v in values]
