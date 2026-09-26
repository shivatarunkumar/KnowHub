"""Create (or update) every KnowHub table in BigQuery, then load the seed rows.

    python infra/gcs/bq/setup_bq.py          # or: make setup-bq
    python infra/gcs/bq/setup_bq.py --plan   # show what would change, touch nothing
    python infra/gcs/bq/setup_bq.py --no-seed

Idempotent, and safe on any machine:
  1. terraform init
  2. import the dataset and any table that already exists in BigQuery but is missing from
     the local state (a second machine, or a deleted terraform.tfstate), so apply updates
     them instead of failing with "Already Exists"
  3. terraform apply: the dataset plus one table per tables/*.json
  4. seed topics and teams from the same files Postgres uses
     (database/postgres/seeds/common), merged by slug, so re-running never duplicates

Settings come from .env (the Makefile sources it): BQ_DB_PROJECT (else GCP_PROJECT_ID),
BQ_DB_DATASET, BQ_DB_LOCATION. Credentials are Application Default Credentials
(gcloud auth application-default login).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="google.auth._default")

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
TABLES_DIR = HERE / "tables"
SEEDS_DIR = REPO_ROOT / "database" / "postgres" / "seeds" / "common"
# seed file → table; the order matters only for readability of the output
SEEDS = {"001_topics.sql": "topics", "002_teams.sql": "teams"}


def settings() -> dict[str, str]:
    project = os.environ.get("BQ_DB_PROJECT", "").strip() or os.environ.get("GCP_PROJECT_ID", "").strip()
    if not project or project == "knowhub-local":
        sys.exit(
            "No GCP project: set BQ_DB_PROJECT (or GCP_PROJECT_ID) in .env to the project that "
            "should own the dataset."
        )
    return {
        "project": project,
        "dataset": os.environ.get("BQ_DB_DATASET", "").strip() or "knowhub",
        "location": os.environ.get("BQ_DB_LOCATION", "").strip() or "europe-west2",
    }


def step(text: str) -> None:
    print(f"\n==> {text}", flush=True)


def terraform(*args: str, capture: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["terraform", f"-chdir={HERE}", *args],
        text=True,
        capture_output=capture,
        check=False,
    )
    if result.returncode != 0:
        if capture:
            sys.stderr.write(result.stdout + result.stderr)
        sys.exit(f"terraform {args[0]} failed (exit {result.returncode})")
    return result


def tf_vars(cfg: dict[str, str]) -> list[str]:
    return [
        f"-var=project={cfg['project']}",
        f"-var=dataset={cfg['dataset']}",
        f"-var=location={cfg['location']}",
    ]


# ------------------------------------------------------------------ import existing
def import_existing(client, cfg: dict[str, str]) -> None:
    """Bring anything that already exists into the state, so apply manages it."""
    from google.api_core.exceptions import NotFound

    listed = (
        terraform("state", "list", capture=True).stdout.split()
        if (HERE / "terraform.tfstate").exists()
        else []
    )
    in_state = set(listed)
    dataset_ref = f"{cfg['project']}.{cfg['dataset']}"
    try:
        dataset = client.get_dataset(dataset_ref)
    except NotFound:
        print(f"    dataset {dataset_ref} does not exist yet: terraform will create it")
        return

    if dataset.location.lower() != cfg["location"].lower():
        sys.exit(
            f"Dataset {dataset_ref} already exists in {dataset.location}, but BQ_DB_LOCATION is "
            f"{cfg['location']}. A dataset cannot move; set BQ_DB_LOCATION={dataset.location} or use "
            "another BQ_DB_DATASET."
        )

    wanted: list[tuple[str, str]] = []
    if "google_bigquery_dataset.knowhub" not in in_state:
        wanted.append(
            ("google_bigquery_dataset.knowhub", f"projects/{cfg['project']}/datasets/{cfg['dataset']}")
        )
    existing = {table.table_id for table in client.list_tables(dataset_ref)}
    for path in sorted(TABLES_DIR.glob("*.json")):
        name = path.stem
        address = f'google_bigquery_table.table["{name}"]'
        if name in existing and address not in in_state:
            wanted.append((address, f"projects/{cfg['project']}/datasets/{cfg['dataset']}/tables/{name}"))

    if not wanted:
        print("    state already matches what exists in BigQuery")
        return
    for address, resource_id in wanted:
        print(f"    importing {address}")
        terraform("import", "-input=false", *tf_vars(cfg), address, resource_id, capture=True)


# ------------------------------------------------------------------ seeds
TUPLE_RE = re.compile(r"^\s*\((.*)\)\s*,?\s*$")
VALUE_RE = re.compile(r"'((?:[^']|'')*)'|(-?\d+)|(NULL)", re.I)


def parse_seed(path: Path) -> tuple[list[str], list[list[str | int | None]]]:
    """Columns and rows from `INSERT INTO t (a, b) VALUES (...), (...) ON CONFLICT ...`.

    The Postgres seed files are the one source of seed data; this reads their VALUES
    list so the two databases can never disagree about which topics and teams exist.
    """
    sql = path.read_text(encoding="utf-8")
    header = re.search(r"INSERT INTO \w+ \(([^)]*)\) VALUES", sql)
    if header is None:
        raise ValueError(f"{path.name}: no INSERT ... VALUES found")
    columns = [c.strip() for c in header.group(1).split(",")]
    body = sql[header.end() : sql.index("ON CONFLICT")]
    rows: list[list[str | int | None]] = []
    for line in body.splitlines():
        match = TUPLE_RE.match(line)  # comment lines don't start with "(", so never match
        if not match:
            continue
        values: list[str | int | None] = []
        for text, number, null in VALUE_RE.findall(match.group(1)):
            if null:
                values.append(None)
            elif number:
                values.append(int(number))
            else:
                values.append(text.replace("''", "'"))
        if len(values) != len(columns):
            raise ValueError(
                f"{path.name}: {len(values)} values for {len(columns)} columns in {line.strip()}"
            )
        rows.append(values)
    return columns, rows


def literal(value: str | int | None) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def merge_sql(table: str, columns: list[str], rows: list[list]) -> str:
    source = ",\n    ".join(
        "STRUCT(" + ", ".join(f"{literal(v)} AS {c}" for c, v in zip(columns, row, strict=True)) + ")"
        for row in rows
    )
    updates = ", ".join(f"{c} = s.{c}" for c in columns if c != "slug")
    return f"""
MERGE `{table}` AS t
USING UNNEST([
    {source}
]) AS s
ON t.slug = s.slug
WHEN MATCHED THEN UPDATE SET {updates}, updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (id, {", ".join(columns)}, is_active, created_at, updated_at)
  VALUES (GENERATE_UUID(), {", ".join(f"s.{c}" for c in columns)}, TRUE,
          CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
"""


def seed(client, cfg: dict[str, str]) -> None:
    for filename, table in SEEDS.items():
        columns, rows = parse_seed(SEEDS_DIR / filename)
        job = client.query(merge_sql(f"{cfg['project']}.{cfg['dataset']}.{table}", columns, rows))
        job.result()
        print(
            f"    {table:<8} {len(rows)} rows from {filename} "
            f"({job.num_dml_affected_rows} inserted or updated)"
        )


# ------------------------------------------------------------------ main
def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--plan", action="store_true", help="show the changes, apply nothing")
    parser.add_argument("--no-seed", action="store_true", help="skip loading topics and teams")
    args = parser.parse_args()

    if shutil.which("terraform") is None:
        sys.exit("terraform is not installed: brew install terraform (1.5 or newer)")
    try:
        from google.cloud import bigquery
    except ImportError:
        sys.exit("google-cloud-bigquery is missing: run make install-python")

    cfg = settings()
    print(
        f"[setup-bq] {cfg['project']}.{cfg['dataset']} in {cfg['location']}, "
        f"{len(list(TABLES_DIR.glob('*.json')))} tables"
    )
    client = bigquery.Client(project=cfg["project"], location=cfg["location"])

    step("terraform init")
    terraform("init", "-input=false", "-upgrade=false", capture=True)
    print("    providers ready")

    step("import what already exists")
    import_existing(client, cfg)

    if args.plan:
        step("terraform plan")
        terraform("plan", "-input=false", *tf_vars(cfg))
        return

    step("terraform apply")
    terraform("apply", "-input=false", "-auto-approve", *tf_vars(cfg))

    if not args.no_seed:
        step("seed topics and teams")
        seed(client, cfg)

    print(
        f"\n✔ BigQuery ready: {cfg['project']}.{cfg['dataset']}. Next: set RUN_ON=BQ in .env, then make api"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
    except json.JSONDecodeError as exc:
        sys.exit(f"a file in {TABLES_DIR} is not valid JSON: {exc}")
