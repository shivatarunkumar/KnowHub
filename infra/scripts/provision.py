"""Provision KnowHub resources: GCS buckets, Pub/Sub topics + subscriptions, AI models.

Every step is idempotent: it creates what is missing and leaves the rest alone.

    python infra/scripts/provision.py --target local          # emulators (default when APP_ENV=local)
    python infra/scripts/provision.py --target gcp            # real project from GCP_PROJECT_ID (uses ADC)
    python infra/scripts/provision.py --only gcs,pubsub       # subset

Project-level setup (enable APIs, service accounts/IAM, Cloud SQL: Phase 10) is added
here when that phase starts.
"""

from __future__ import annotations

import argparse
import os

import resources

STEPS = ("gcs", "pubsub", "bigquery", "ai")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    default_target = "local" if os.environ.get("APP_ENV", "local") == "local" else "gcp"
    parser.add_argument("--target", choices=["local", "gcp"], default=default_target)
    parser.add_argument("--only", default=",".join(STEPS), help=f"comma-separated subset of {STEPS}")
    args = parser.parse_args()
    steps = [s.strip() for s in args.only.split(",") if s.strip()]
    unknown = set(steps) - set(STEPS)
    if unknown:
        parser.error(f"unknown step(s): {', '.join(sorted(unknown))}")

    if args.target == "local":
        # Refuse to touch real GCP by accident: local runs must point at the emulators.
        resources.env("GCS_ENDPOINT_URL")
        resources.env("PUBSUB_EMULATOR_HOST")
    else:
        os.environ.pop("PUBSUB_EMULATOR_HOST", None)
        os.environ.pop("STORAGE_EMULATOR_HOST", None)

    print(
        f"[provision] target={args.target} project={resources.env('GCP_PROJECT_ID')} steps={','.join(steps)}"
    )

    if "gcs" in steps:
        import gcs

        gcs.ensure_buckets(args.target, resources.buckets())

    if "pubsub" in steps:
        import pubsub

        pubsub.ensure_pubsub(args.target, resources.topics(), resources.subscriptions())

    if "bigquery" in steps:
        import bigquery as bq

        bq.ensure_bigquery(args.target)

    if "ai" in steps:
        provider = os.environ.get("AI_PROVIDER", "none")
        pull = os.environ.get("AI_PULL_MODELS", "true").lower() == "true"
        if provider == "ollama" and pull:
            import ai_models

            ai_models.ensure_models(resources.ai_models())
        else:
            print(f"[provision] ai: skipped (AI_PROVIDER={provider}, AI_PULL_MODELS={pull})")

    print("[provision] done")


if __name__ == "__main__":
    main()
