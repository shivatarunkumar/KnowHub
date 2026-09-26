"""infra/gcs/bq/tables must mirror the Postgres migrations.

Every table the migrations create has a JSON file with the same columns, compatible
types and the same NOT NULL-ness, except for the differences project-bq.md documents.
A new migration that isn't mirrored for BigQuery fails here.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "database" / "postgres" / "migrations"
TABLES = ROOT / "infra" / "gcs" / "bq" / "tables"

# Deliberately absent in BigQuery (see project-bq.md, "What is different").
COMPUTED_ON_READ = {
    "videos": {"view_count", "like_count", "comment_count", "search_vector"},
    "comments": {"like_count"},
    "users": {"subscriber_count"},
}
TYPE_OVERRIDES = {("analytics_events", "id"): "STRING"}  # bigint identity → UUID string
PG_TO_BQ = {
    "uuid": "STRING",
    "text": "STRING",
    "inet": "STRING",
    "timestamptz": "TIMESTAMP",
    "integer": "INT64",
    "bigint": "INT64",
    "smallint": "INT64",
    "boolean": "BOOL",
    "jsonb": "JSON",
    "vector": "FLOAT64",
}
COLUMN_RE = re.compile(
    r"^\s+(\w+)\s+(uuid|text|timestamptz|integer|bigint|smallint|boolean|jsonb|inet|vector|tsvector)\b(.*)$"
)


def postgres_tables() -> dict[str, dict[str, tuple[str, bool]]]:
    """{table: {column: (pg type, not null)}} from CREATE TABLE and ALTER TABLE ADD COLUMN."""
    tables: dict[str, dict[str, tuple[str, bool]]] = {}
    for path in sorted(MIGRATIONS.glob("V*.sql")):
        sql = path.read_text(encoding="utf-8")
        for match in re.finditer(r"CREATE TABLE (\w+) \((.*?)\n\);", sql, re.S):
            name, body = match.groups()
            columns = {}
            for line in body.splitlines():
                col = COLUMN_RE.match(line)
                if col:
                    column, pg_type, rest = col.groups()
                    columns[column] = (pg_type, "NOT NULL" in rest or "PRIMARY KEY" in rest)
            # composite primary keys make their columns NOT NULL too
            for pk in re.findall(r"PRIMARY KEY \(([^)]*)\)", body):
                for column in (c.strip() for c in pk.split(",")):
                    columns[column] = (columns[column][0], True)
            tables[name] = columns
        for table, column, pg_type, rest in re.findall(
            r"ALTER TABLE (\w+) ADD COLUMN (\w+) (\w+)([^;]*);", sql
        ):
            tables[table][column] = (pg_type, "NOT NULL" in rest)
    return tables


def bq_tables() -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(TABLES.glob("*.json"))}


PG = postgres_tables()
BQ = bq_tables()


def test_every_table_is_mirrored():
    assert sorted(set(PG) - set(BQ)) == [], "add a tables/<name>.json for each new Postgres table"
    assert sorted(set(BQ) - set(PG)) == [], "a BigQuery table with no Postgres migration"


@pytest.mark.parametrize("table", sorted(PG))
def test_columns_match(table):
    pg_columns = set(PG[table]) - COMPUTED_ON_READ.get(table, set())
    bq_columns = {field["name"] for field in BQ[table]["schema"]}
    assert bq_columns == pg_columns, {
        "missing in BigQuery": pg_columns - bq_columns,
        "extra": bq_columns - pg_columns,
    }


@pytest.mark.parametrize("table", sorted(PG))
def test_types_and_nullability_match(table):
    fields = {field["name"]: field for field in BQ[table]["schema"]}
    wrong = []
    for column, (pg_type, not_null) in PG[table].items():
        if column not in fields:
            continue
        field = fields[column]
        expected = TYPE_OVERRIDES.get((table, column), PG_TO_BQ[pg_type])
        if field["type"] != expected:
            wrong.append(f"{column}: {field['type']} (expected {expected})")
        if pg_type == "vector":
            if field["mode"] != "REPEATED":
                wrong.append(f"{column}: vectors are REPEATED FLOAT64")
        elif (field["mode"] == "REQUIRED") != not_null:
            wrong.append(f"{column}: mode {field['mode']} but Postgres NOT NULL={not_null}")
    assert wrong == []


@pytest.mark.parametrize("table", sorted(BQ))
def test_keys_and_clustering_name_real_columns(table):
    spec = BQ[table]
    names = {field["name"] for field in spec["schema"]}
    assert set(spec["primary_key"]) <= names
    assert set(spec["clustering"]) <= names and 1 <= len(spec["clustering"]) <= 4
    if "time_partitioning" in spec:
        assert spec["time_partitioning"]["field"] in names
