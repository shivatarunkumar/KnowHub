"""Create the BigQuery dataset (if missing) and apply database/bigquery/ddl/*.sql.

GCP only: BigQuery has no emulator, so local analytics go to Postgres instead
(ANALYTICS_BACKEND=postgres). Every statement is CREATE ... IF NOT EXISTS or
CREATE OR REPLACE VIEW, so re-running is safe and never drops data.
"""

from __future__ import annotations

import os
from pathlib import Path

from google.api_core import exceptions
from google.cloud import bigquery
from resources import env

DDL_DIR = Path(__file__).resolve().parents[2] / "database" / "bigquery" / "ddl"


def ensure_dataset(client: bigquery.Client, dataset_id: str, location: str) -> None:
    try:
        existing = client.get_dataset(dataset_id)
        print(f"[provision] bigquery dataset {dataset_id}: exists (location {existing.location})")
        if existing.location.upper() != location.upper():
            print(
                f"[provision] WARNING: dataset location is {existing.location}, but BQ_LOCATION is "
                f"{location}; using the dataset's location"
            )
    except exceptions.NotFound:
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = location
        dataset.description = "KnowHub analytics events"
        client.create_dataset(dataset)
        print(f"[provision] bigquery dataset {dataset_id}: created in {location}")


def apply_ddl(client: bigquery.Client, project: str, dataset: str) -> None:
    files = sorted(DDL_DIR.glob("*.sql"))
    if not files:
        print(f"[provision] WARNING: no DDL files in {DDL_DIR}")
        return
    for path in files:
        sql = path.read_text(encoding="utf-8").replace("${project}", project).replace("${dataset}", dataset)
        client.query(sql).result()
        print(f"[provision] bigquery ddl {path.name}: applied")


def ensure_bigquery(target: str) -> None:
    if target != "gcp":
        print("[provision] bigquery: skipped (local analytics go to Postgres)")
        return
    project = os.environ.get("BQ_PROJECT_ID") or env("GCP_PROJECT_ID")
    dataset_name = env("BQ_DATASET")
    location = os.environ.get("BQ_LOCATION", "US")
    dataset_id = f"{project}.{dataset_name}"

    client = bigquery.Client(project=project)
    ensure_dataset(client, dataset_id, location)
    apply_ddl(client, project, dataset_name)
