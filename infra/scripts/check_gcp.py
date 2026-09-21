"""Check the GCP connection and resources — without starting the API.

    python infra/scripts/check_gcp.py            # or: make check-gcp
    python infra/scripts/check_gcp.py --no-write # skip the upload/delete probe

The API's /health only reports "timed out" when something is wrong. This tells you which
part is wrong: configuration, credentials, the network (proxy/firewall), permissions, or a
missing bucket/topic. Exits non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import warnings
from pathlib import Path

# We report the quota-project mismatch ourselves, once, instead of letting the auth
# library print the same warning before every call.
warnings.filterwarnings("ignore", category=UserWarning, module="google.auth._default")

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import resources  # noqa: E402

API_TIMEOUT = 10  # seconds per call: fail fast rather than hang like the health check
TCP_TIMEOUT = 5
ENDPOINTS = ("oauth2.googleapis.com", "storage.googleapis.com", "pubsub.googleapis.com")
ADC_PATH = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"


class Report:
    def __init__(self, title: str) -> None:
        print(f"\n[check-gcp] {title}\n")
        self.failed = 0

    def ok(self, name: str, detail: str = "") -> None:
        print(f"  \033[32mok\033[0m    {name:<14} {detail}")

    def warn(self, name: str, detail: str, hint: str = "") -> None:
        print(f"  \033[33mwarn\033[0m  {name:<14} {detail}")
        if hint:
            print(f"        {'':<14} → {hint}")

    def fail(self, name: str, detail: str, hint: str = "") -> None:
        self.failed += 1
        print(f"  \033[31mFAIL\033[0m  {name:<14} {detail}")
        if hint:
            print(f"        {'':<14} → {hint}")

    def finish(self) -> int:
        if self.failed:
            print(f"\n{self.failed} check(s) failed\n")
            return 1
        print("\nall checks passed\n")
        return 0


def load_env() -> None:
    env_file = REPO_ROOT / ".env"
    if not env_file.is_file():
        sys.exit("[check-gcp] ERROR: no .env file. Copy .env.example to .env first.")
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def describe(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}".strip().splitlines()[0][:200]


# ----------------------------------------------------------------- checks
def check_config(report: Report) -> tuple[str, str, bool]:
    project = os.environ.get("GCP_PROJECT_ID", "")
    bucket = os.environ.get("GCS_BUCKET", "")
    emulator = bool(os.environ.get("GCS_ENDPOINT_URL") or os.environ.get("PUBSUB_EMULATOR_HOST"))
    if not project:
        report.fail("config", "GCP_PROJECT_ID is not set", "set it in .env")
    elif project == "knowhub-local" and not emulator:
        report.fail(
            "config",
            "GCP_PROJECT_ID is still the placeholder 'knowhub-local' but no emulator is configured",
            "set GCP_PROJECT_ID to your real project, or point GCS_ENDPOINT_URL at the emulator",
        )
    else:
        report.ok("config", f"project={project} bucket={bucket or '(unset)'}")
    if emulator:
        report.ok(
            "mode",
            f"emulator — GCS_ENDPOINT_URL={os.environ.get('GCS_ENDPOINT_URL', '') or '(unset)'} "
            f"PUBSUB_EMULATOR_HOST={os.environ.get('PUBSUB_EMULATOR_HOST', '') or '(unset)'}",
        )
    else:
        report.ok("mode", "real GCP (no emulator endpoints set)")
    return project, bucket, emulator


def check_network(report: Report) -> bool:
    """A corporate laptop usually fails here, and that is what a 15s timeout really means."""
    proxy = {k: v for k, v in os.environ.items() if k.lower() in ("https_proxy", "http_proxy", "no_proxy")}
    if proxy:
        report.warn("proxy", ", ".join(f"{k}={v}" for k, v in proxy.items()), "these apply to API calls too")
    unreachable = []
    for host in ENDPOINTS:
        try:
            with socket.create_connection((host, 443), timeout=TCP_TIMEOUT):
                pass
        except OSError as exc:
            unreachable.append(f"{host} ({exc.__class__.__name__})")
    if unreachable:
        report.fail(
            "network",
            f"cannot reach {', '.join(unreachable)}",
            "you are offline, behind a firewall, or need HTTPS_PROXY set. This is what makes "
            "the API's storage/pubsub checks time out",
        )
        return False
    report.ok("network", f"reached {', '.join(ENDPOINTS)} on 443")
    return True


def check_credentials(report: Report, project: str) -> bool:
    key_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if key_file and not Path(key_file).is_file():
        report.fail("credentials", f"GOOGLE_APPLICATION_CREDENTIALS points at a missing file: {key_file}")
        return False
    if not key_file and not ADC_PATH.is_file():
        report.fail(
            "credentials",
            "no Application Default Credentials on this machine",
            "run: gcloud auth application-default login",
        )
        return False

    import google.auth
    import google.auth.transport.requests

    try:
        credentials, detected = google.auth.default()
        credentials.refresh(google.auth.transport.requests.Request())
    except Exception as exc:
        report.fail(
            "credentials",
            describe(exc),
            "run: gcloud auth application-default login",
        )
        return False

    who = getattr(credentials, "service_account_email", None) or getattr(
        credentials, "quota_project_id", None
    )
    source = key_file or str(ADC_PATH)
    report.ok("credentials", f"valid token ({who or 'user account'}) from {source}")
    if detected and project and detected != project:
        report.warn(
            "quota project",
            f"credentials default to '{detected}', .env says '{project}'",
            f"run: gcloud auth application-default set-quota-project {project}",
        )
    return True


def check_bucket(report: Report, project: str, bucket_name: str, emulator: bool, write: bool) -> None:
    if not bucket_name:
        report.fail("bucket", "GCS_BUCKET is not set", "set it in .env")
        return

    from google.api_core import exceptions
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import storage

    try:
        if emulator and os.environ.get("GCS_ENDPOINT_URL"):
            client = storage.Client(
                project=project,
                credentials=AnonymousCredentials(),
                client_options={"api_endpoint": os.environ["GCS_ENDPOINT_URL"]},
            )
        else:
            client = storage.Client(project=project)
        bucket = client.lookup_bucket(bucket_name, timeout=API_TIMEOUT)
    except exceptions.Forbidden as exc:
        report.fail("bucket", describe(exc), f"the account needs roles/storage.objectAdmin on {bucket_name}")
        return
    except Exception as exc:
        report.fail("bucket", describe(exc), "check the project, the network and your credentials")
        return

    if bucket is None:
        report.fail(
            "bucket",
            f"gs://{bucket_name} does not exist (or is invisible to this account)",
            f"create it, or run: make provision. Check the name in .env and the project '{project}'",
        )
        return
    report.ok("bucket", f"gs://{bucket_name} exists ({bucket.location or 'unknown location'})")

    raw, media = os.environ.get("GCS_RAW_PREFIX", "raw"), os.environ.get("GCS_MEDIA_PREFIX", "media")
    try:
        counted = {
            prefix: sum(
                1
                for _ in client.list_blobs(
                    bucket_name, prefix=f"{prefix}/", max_results=5, timeout=API_TIMEOUT
                )
            )
            for prefix in (raw, media)
        }
        report.ok("read", ", ".join(f"{p}/ {'has objects' if n else 'empty'}" for p, n in counted.items()))
    except exceptions.Forbidden as exc:
        report.fail("read", describe(exc), "the account needs at least roles/storage.objectViewer")
    except Exception as exc:
        report.fail("read", describe(exc))

    if not write:
        report.warn("write", "skipped (--no-write)")
        return
    probe = bucket.blob(f"{media}/_checks/connectivity.txt")
    try:
        probe.upload_from_string("knowhub check-gcp", content_type="text/plain", timeout=API_TIMEOUT)
        probe.delete(timeout=API_TIMEOUT)
        report.ok("write", f"uploaded and deleted {probe.name}")
    except exceptions.Forbidden as exc:
        report.fail(
            "write",
            describe(exc),
            "uploads will fail: the account needs roles/storage.objectAdmin (or objectCreator)",
        )
    except Exception as exc:
        report.fail("write", describe(exc))


def check_pubsub(report: Report, project: str) -> None:
    from google.api_core import exceptions
    from google.cloud import pubsub_v1

    wanted_topics = [spec.name for spec in resources.topics()]
    wanted_subs = [spec.name for spec in resources.subscriptions()]
    try:
        publisher = pubsub_v1.PublisherClient()
        existing = {
            path.rsplit("/", 1)[-1]
            for path in (
                topic.name
                for topic in publisher.list_topics(
                    request={"project": f"projects/{project}"}, timeout=API_TIMEOUT
                )
            )
        }
    except exceptions.PermissionDenied as exc:
        report.fail("topics", describe(exc), "the account needs roles/pubsub.editor on the project")
        return
    except Exception as exc:
        report.fail("topics", describe(exc), "check the project, the network and your credentials")
        return

    missing = [name for name in wanted_topics if name not in existing]
    if missing:
        report.fail("topics", f"missing: {', '.join(missing)}", "create them, or run: make provision")
    else:
        report.ok("topics", f"all {len(wanted_topics)} present")

    try:
        subscriber = pubsub_v1.SubscriberClient()
        have = {
            sub.name.rsplit("/", 1)[-1]
            for sub in subscriber.list_subscriptions(
                request={"project": f"projects/{project}"}, timeout=API_TIMEOUT
            )
        }
        subscriber.close()
    except Exception as exc:
        report.warn("subscriptions", describe(exc))
        return
    missing_subs = [name for name in wanted_subs if name not in have]
    if missing_subs:
        report.warn(
            "subscriptions",
            f"missing: {', '.join(missing_subs)}",
            "nothing consumes them yet (the workers are a later phase); run make provision to create them",
        )
    else:
        report.ok("subscriptions", f"all {len(wanted_subs)} present")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-write", action="store_true", help="skip the upload/delete probe")
    args = parser.parse_args()

    load_env()
    report = Report("checking configuration, credentials, bucket and Pub/Sub")
    project, bucket, emulator = check_config(report)
    if not project:
        return report.finish()

    if emulator:
        report.ok("credentials", "not needed in emulator mode")
    else:
        if not check_network(report):
            return report.finish()  # every API call would just time out
        if not check_credentials(report, project):
            return report.finish()

    check_bucket(report, project, bucket, emulator, write=not args.no_write)
    check_pubsub(report, project)
    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
