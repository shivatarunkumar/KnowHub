"""Check the database connection, schema and seed data — without starting the API.

    python database/scripts/check_db.py          # or: make check-db

Every check prints ok or FAIL with what to do about it. Exits non-zero if any fails,
so it can gate a script or a CI job.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import MIGRATIONS_DIR, sync_url, url_host, url_parts  # noqa: E402
from migrate import load_migrations  # noqa: E402

CONNECT_TIMEOUT = 5
WANTED_EXTENSIONS = ("pg_trgm", "vector")


class Report:
    """Collects the ok/FAIL lines and remembers whether anything failed."""

    def __init__(self, title: str) -> None:
        print(f"\n[check-db] {title}\n")
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
        sys.exit("[check-db] ERROR: no .env file. Copy .env.example to .env first.")
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def for_this_host(url: str) -> str:
    if not Path("/.dockerenv").exists():
        url = url.replace("host.docker.internal", "localhost").replace("@postgres:", "@localhost:")
    return sync_url(url)


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT):
            return True
    except OSError:
        return False


def check_reachable(report: Report, url: str) -> bool:
    """TCP first: 'connection refused' and 'wrong password' need different fixes."""
    host = url_host(url) or "localhost"
    port = int(url.rsplit(":", 1)[-1].split("/")[0]) if ":" in url.rsplit("@", 1)[-1] else 5432
    if port_open(host, port):
        report.ok("server", f"{host}:{port} is accepting connections")
        return True
    report.fail(
        "server",
        f"nothing is listening on {host}:{port}",
        f"start PostgreSQL (brew services start postgresql@17), or fix the host/port in "
        f"DATABASE_URL. Check with: pg_isready -h {host} -p {port}",
    )
    return False


def connect(report: Report, url: str, name: str, hint_role: str) -> psycopg.Connection | None:
    user, _, database = url_parts(url)
    try:
        conn = psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT)
    except psycopg.OperationalError as exc:
        message = str(exc).strip().splitlines()[0]
        hint = hint_role
        if "password authentication failed" in message or "no password supplied" in message:
            hint = f"the password for '{user}' in the URL is wrong"
        elif "does not exist" in message and "database" in message:
            hint = f"database '{database}' does not exist — run: make db-init"
        elif "does not exist" in message and "role" in message:
            hint = f"role '{user}' does not exist — run: make db-init"
        report.fail(name, message, hint)
        return None
    report.ok(name, f"{user}@{url_host(url)}/{database}")
    return conn


def scalar(conn: psycopg.Connection, sql: str):
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
    return row[0] if row else None


def check_schema(report: Report, conn: psycopg.Connection) -> None:
    report.ok("version", (scalar(conn, "SELECT version()") or "").split(" on ")[0])

    with conn.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension WHERE extname = ANY(%s)", (list(WANTED_EXTENSIONS),))
        present = sorted(row[0] for row in cur.fetchall())
    missing = [name for name in WANTED_EXTENSIONS if name not in present]
    if missing:
        report.fail(
            "extensions",
            f"missing: {', '.join(missing)} (have: {', '.join(present) or 'none'})",
            "install pgvector (brew install pgvector) and run: make db-init",
        )
    else:
        report.ok("extensions", ", ".join(present))

    tables = scalar(conn, "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'") or 0
    if tables == 0:
        report.fail("tables", "the public schema is empty", "run: make db-init")
        return
    report.ok("tables", f"{tables} in the public schema")

    if not scalar(conn, "SELECT to_regclass('public.schema_migrations') IS NOT NULL"):
        report.fail("migrations", "no schema_migrations table", "run: make db-init")
        return
    applied = scalar(conn, "SELECT count(*) FROM schema_migrations") or 0
    latest = scalar(conn, "SELECT max(version) FROM schema_migrations") or 0
    on_disk = load_migrations(MIGRATIONS_DIR)
    pending = [m for m in on_disk if m.version > latest]
    if pending:
        report.fail(
            "migrations",
            f"{applied} applied (latest V{latest:03d}), {len(pending)} pending: "
            f"{', '.join(m.path.name for m in pending[:3])}",
            "run: make db-init",
        )
    else:
        report.ok("migrations", f"{applied} applied, latest V{latest:03d} of {len(on_disk)} files")

    topics = scalar(conn, "SELECT count(*) FROM topics") or 0
    if topics:
        report.ok("seed data", f"{topics} topics")
    else:
        report.warn("seed data", "no topics", "run: make db-init (the feed's topic chips need them)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="override DATABASE_URL")
    args = parser.parse_args()

    load_env()
    database_url = for_this_host(args.database_url or os.environ.get("DATABASE_URL", ""))
    admin_url = for_this_host(os.environ.get("POSTGRES_ADMIN_URL", ""))
    if not database_url:
        sys.exit("[check-db] ERROR: DATABASE_URL is not set (see .env.example)")

    user, _, database = url_parts(database_url)
    report = Report(f"{user}@{url_host(database_url)}/{database}")

    if not check_reachable(report, database_url):
        return report.finish()

    conn = connect(report, database_url, "app login", "check DATABASE_URL in .env")
    if conn is not None:
        with conn:
            check_schema(report, conn)

    if admin_url:
        admin = connect(report, admin_url, "admin login", "check POSTGRES_ADMIN_URL in .env")
        if admin is not None:
            admin.close()
    else:
        report.warn("admin login", "POSTGRES_ADMIN_URL is not set", "make db-init needs it")

    return report.finish()


if __name__ == "__main__":
    sys.exit(main())
