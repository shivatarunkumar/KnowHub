"""Create GCS buckets (fake-gcs-server locally, real GCS on GCP). Idempotent."""

from __future__ import annotations

import time

from google.api_core import exceptions
from google.auth.credentials import AnonymousCredentials
from google.cloud import storage
from resources import BucketSpec, env


def make_client(target: str) -> storage.Client:
    project = env("GCP_PROJECT_ID")
    if target == "local":
        return storage.Client(
            project=project,
            credentials=AnonymousCredentials(),
            client_options={"api_endpoint": env("GCS_ENDPOINT_URL")},
        )
    return storage.Client(project=project)


def wait_ready(client: storage.Client, seconds: int = 60) -> None:
    deadline = time.monotonic() + seconds
    while True:
        try:
            list(client.list_buckets(max_results=1))
            return
        except Exception as exc:  # emulator still starting: connection refused etc.
            if time.monotonic() >= deadline:
                raise SystemExit(f"[provision] ERROR: storage not reachable: {exc}") from exc
            time.sleep(1)


def ensure_buckets(target: str, specs: list[BucketSpec]) -> None:
    client = make_client(target)
    wait_ready(client)
    for spec in specs:
        bucket = client.lookup_bucket(spec.name)
        if bucket is None:
            try:
                if target == "local":
                    bucket = client.create_bucket(spec.name)
                else:
                    bucket = storage.Bucket(client, spec.name)
                    bucket.iam_configuration.uniform_bucket_level_access_enabled = True
                    bucket = client.create_bucket(bucket, location=env("GCP_REGION"))
                print(f"[provision] bucket {spec.name}: created ({spec.purpose})")
            except exceptions.Conflict:
                bucket = client.get_bucket(spec.name)
                print(f"[provision] bucket {spec.name}: exists")
        else:
            print(f"[provision] bucket {spec.name}: exists")

        if target == "gcp":
            apply_gcp_settings(bucket, spec)


def apply_gcp_settings(bucket: storage.Bucket, spec: BucketSpec) -> None:
    """CORS for browser uploads and lifecycle rules; re-applied on every run."""
    if spec.cors_origins:
        bucket.cors = [
            {
                "origin": list(spec.cors_origins),
                "method": ["PUT", "POST", "GET", "HEAD", "OPTIONS"],
                "responseHeader": ["Content-Type", "Content-Range", "x-goog-resumable", "Location"],
                "maxAgeSeconds": 3600,
            }
        ]
    if spec.coldline_after_days:
        bucket.clear_lifecycle_rules()
        bucket.add_lifecycle_set_storage_class_rule(
            "COLDLINE",
            age=spec.coldline_after_days,
            matches_prefix=[spec.coldline_prefix] if spec.coldline_prefix else None,
        )
    bucket.patch()
    print(f"[provision] bucket {spec.name}: settings applied")
