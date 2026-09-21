"""Set up the whole KnowHub database in one command.

Runs, in order, skipping whatever already exists:

    1. init_db.sql   role, database, privileges, extensions   (as the admin user)
    2. migrations    every pending V<NNN>__*.sql file          (as the app user)
    3. seeds         seeds/common + seeds/$APP_ENV             (as the app user)
    4. verify        report tables, migrations and seeded rows

Safe to run any number of times: existing objects are left alone.

    python database/scripts/setup_db.py                 # create / update everything
    python database/scripts/setup_db.py --skip-seed     # schema only
    python database/scripts/setup_db.py --reset --yes   # DROP the database first (local only)
    python database/scripts/setup_db.py --database-url postgresql://user:pw@host:5432/db

Connection settings come from .env (DATABASE_URL, POSTGRES_ADMIN_URL) unless overridden
by the flags above.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import psycopg
from psycopg import sql

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _db import MIGRATIONS_DIR, sync_url, url_host, url_parts  # noqa: E402
from migrate import MigrationError  # noqa: E402
from migrate import run as run_migrations  # noqa: E402
from seed import run_seeds, seed_files  # noqa: E402

INIT_DB_SQL = REPO_ROOT / "database" / "postgres" / "init_db.sql"
ENV_FILE = REPO_ROOT / ".env"

log = logging.getLogger("setup_db")


class SetupError(Exception):
    """Something the user can fix, reported without a traceback."""


# --------------------------------------------------------------------------- config
def load_env_file(path: Path) -> None:
    """Fill in missing environment variables from .env (real env wins)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def running_in_container() -> bool:
    return Path("/.dockerenv").exists()


def for_this_host(url: str, label: str) -> str:
    """.env holds container hostnames; rewrite them when running on the host."""
    if not running_in_container() and "host.docker.internal" in url:
        log.info("%s points at host.docker.internal; using localhost (running outside docker)", label)
        return url.replace("host.docker.internal", "localhost")
    return url


def resolve_urls(args: argparse.Namespace) -> tuple[str, str]:
    load_env_file(ENV_FILE)
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    admin_url = args.admin_url or os.environ.get("POSTGRES_ADMIN_URL")
    if not database_url:
        raise SetupError("DATABASE_URL is not set: copy .env.example to .env, or pass --database-url")
    if not admin_url:
        raise SetupError("POSTGRES_ADMIN_URL is not set: copy .env.example to .env, or pass --admin-url")
    database_url = for_this_host(sync_url(database_url), "DATABASE_URL")
    admin_url = for_this_host(sync_url(admin_url), "POSTGRES_ADMIN_URL")
    os.environ["DATABASE_URL"] = database_url  # migrate.py / seed.py read this
    return admin_url, database_url


# --------------------------------------------------------------------------- helpers
def connect(url: str, *, autocommit: bool = False, what: str = "database") -> psycopg.Connection:
    try:
        return psycopg.connect(url, autocommit=autocommit, connect_timeout=10)
    except psycopg.OperationalError as exc:
        detail = str(exc).strip().splitlines()[0] if str(exc).strip() else exc
        host = url_host(url)
        hint = "is PostgreSQL running, and are the host/port right?"
        auth_problem = "password authentication failed" in str(exc) or (
            "role" in str(exc) and "does not exist" in str(exc)
        )
        if auth_problem:
            hint = "check the user and password in DATABASE_URL / POSTGRES_ADMIN_URL"
        raise SetupError(f"cannot connect to the {what} at {host}: {detail}\n  → {hint}") from exc


def wait_for_server(admin_url: str, seconds: int) -> None:
    deadline = time.monotonic() + seconds
    attempt = 0
    while True:
        attempt += 1
        try:
            with connect(admin_url, autocommit=True, what="server"):
                return
        except SetupError:
            if time.monotonic() >= deadline:
                raise
            if attempt == 1:
                log.info("waiting for PostgreSQL at %s …", url_host(admin_url))
            time.sleep(2)


def server_version(admin_url: str) -> str:
    with connect(admin_url, autocommit=True, what="server") as conn:
        return conn.execute("SELECT version()").fetchone()[0].split(" on ")[0]


# --------------------------------------------------------------------------- steps
def step_reset(admin_url: str, db_name: str, confirmed: bool) -> None:
    if os.environ.get("APP_ENV", "local") != "local":
        raise SetupError("--reset only runs with APP_ENV=local")
    if not confirmed:
        raise SetupError(f"--reset deletes the '{db_name}' database and all its data; add --yes")
    log.warning("dropping database %s", db_name)
    with connect(admin_url, autocommit=True, what="server") as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(db_name)))
    log.info("database %s dropped", db_name)


def step_init_db(admin_url: str, db_user: str, db_password: str, db_name: str) -> None:
    """Step 1: role, database, privileges, extensions (init_db.sql, as admin)."""
    if not INIT_DB_SQL.is_file():
        raise SetupError(f"missing {INIT_DB_SQL.relative_to(REPO_ROOT)}")
    if not shutil.which("psql"):
        raise SetupError(
            "psql is not installed, and init_db.sql needs it.\n"
            "  → macOS: brew install libpq (or postgresql), or run this inside the init container: "
            "docker compose run --rm init python database/scripts/setup_db.py"
        )
    log.info("running init_db.sql (role %s, database %s)", db_user, db_name)
    result = subprocess.run(
        [
            "psql",
            admin_url,
            "--no-psqlrc",
            "--quiet",
            "-v",
            "ON_ERROR_STOP=1",
            "-v",
            f"db_name={db_name}",
            "-v",
            f"db_user={db_user}",
            "-v",
            f"db_password={db_password}",
            "-f",
            str(INIT_DB_SQL),
        ],
        capture_output=True,
        text=True,
    )
    for line in (result.stdout + result.stderr).splitlines():
        line = line.strip()
        if not line or line.startswith("=="):
            continue
        if "already exists, skipping" in line:
            log.info("  %s", line.replace("psql:", "").split("NOTICE:")[-1].strip())
        elif result.returncode != 0:
            log.error("  %s", line)
        else:
            log.debug("  %s", line)
    if result.returncode != 0:
        raise SetupError("init_db.sql failed (see the errors above)")
    log.info("step 1/3 done: role, database, privileges and extensions are in place")


def step_migrate(database_url: str) -> None:
    """Step 2: create/alter tables from the versioned migration files."""
    pending_before = migration_state(database_url)
    log.info("applying migrations from %s", MIGRATIONS_DIR.relative_to(REPO_ROOT))
    try:
        run_migrations("up", url=database_url)
    except MigrationError as exc:
        raise SetupError(str(exc)) from exc
    except psycopg.Error as exc:
        raise SetupError(explain_db_error(exc)) from exc
    log.info("step 2/3 done: %s", pending_before)


MISSING_EXTENSION_HINT = (
    "  → this server doesn't have that extension installed.\n"
    "     macOS:  brew install pgvector && brew services restart postgresql@16\n"
    "     docker: use the pgvector/pgvector image (the bundled compose Postgres has it)\n"
    "     After installing it, re-run this script: earlier migrations stay applied."
)


def explain_db_error(exc: psycopg.Error) -> str:
    """Turn a Postgres error into something the reader can act on."""
    message = str(exc).strip()
    first_line = message.splitlines()[0] if message else type(exc).__name__
    if "is not available" in message and "extension" in message:
        return f"migration failed: {first_line}\n{MISSING_EXTENSION_HINT}"
    if "permission denied" in message or "must be owner" in message:
        return (
            f"migration failed: {first_line}\n"
            "  → the app role lacks rights; re-run init_db.sql as a superuser (step 1)"
        )
    if "already exists" in message:
        return (
            f"migration failed: {first_line}\n"
            "  → an object from this migration is already in the database. Drop it, or rebuild "
            "with --reset --yes (local only)"
        )
    return f"migration failed: {type(exc).__name__}: {first_line}"


def migration_state(database_url: str) -> str:
    """How many migrations were already applied, for the "nothing to do" message."""
    with connect(database_url, what="database") as conn:
        table_exists = conn.execute("SELECT to_regclass('schema_migrations')").fetchone()[0]
        applied = conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] if table_exists else 0
    total = len(list(MIGRATIONS_DIR.glob("*.sql")))
    return f"{applied} of {total} migration files were already applied before this run"


def step_seed(database_url: str) -> None:
    """Step 3: idempotent seed data (topic list, and local demo data later)."""
    app_env = os.environ.get("APP_ENV", "local")
    files = seed_files(app_env)
    if not files:
        log.info("step 3/3 skipped: no seed files for APP_ENV=%s", app_env)
        return
    log.info("loading %d seed file(s) for APP_ENV=%s", len(files), app_env)
    try:
        run_seeds(database_url)
    except psycopg.Error as exc:
        raise SetupError(f"seeding failed: {type(exc).__name__}: {exc}") from exc
    log.info("step 3/3 done: seed data is up to date")


def step_verify(database_url: str, db_name: str) -> None:
    with connect(database_url, what="database") as conn:
        tables = conn.execute("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'").fetchone()[0]
        migrations = conn.execute(
            "SELECT count(*), coalesce(max(version), 0) FROM schema_migrations"
        ).fetchone()
        extensions = conn.execute(
            "SELECT string_agg(extname, ', ' ORDER BY extname) FROM pg_extension "
            "WHERE extname IN ('pg_trgm', 'vector')"
        ).fetchone()[0]
        topics = conn.execute("SELECT count(*) FROM topics").fetchone()[0]
    log.info(
        "verify: database=%s tables=%d migrations=%d (latest V%03d) extensions=%s topics=%d",
        db_name,
        tables,
        migrations[0],
        migrations[1],
        extensions or "none",
        topics,
    )


# --------------------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--database-url", help="override DATABASE_URL")
    parser.add_argument("--admin-url", help="override POSTGRES_ADMIN_URL (superuser)")
    parser.add_argument("--skip-seed", action="store_true", help="create the schema but load no data")
    parser.add_argument("--reset", action="store_true", help="DROP the database first (APP_ENV=local)")
    parser.add_argument("--yes", action="store_true", help="confirm --reset")
    parser.add_argument(
        "--wait",
        type=int,
        default=30,
        metavar="SECONDS",
        help="how long to wait for the server to accept connections (default 30)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="show every statement's output")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    started = time.monotonic()
    try:
        admin_url, database_url = resolve_urls(args)
        db_user, db_password, db_name = url_parts(database_url)
        log.info("KnowHub database setup → %s@%s/%s", db_user, url_host(database_url), db_name)

        wait_for_server(admin_url, args.wait)
        log.info("server: %s", server_version(admin_url))

        if args.reset:
            step_reset(admin_url, db_name, args.yes)

        step_init_db(admin_url, db_user, db_password, db_name)
        step_migrate(database_url)
        if args.skip_seed:
            log.info("step 3/3 skipped (--skip-seed)")
        else:
            step_seed(database_url)
        step_verify(database_url, db_name)

        log.info('all done in %.1fs — connect with: psql "%s"', time.monotonic() - started, database_url)
        return 0
    except SetupError as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.error("interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
