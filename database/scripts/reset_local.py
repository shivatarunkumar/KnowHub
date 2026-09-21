"""Drop and rebuild the LOCAL database: drop → init_db.sql → migrate → seed.

Refuses to run unless APP_ENV=local and --yes is given.

    python database/scripts/reset_local.py --yes
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from _db import admin_url, connect, database_url, fail, log, url_parts
from migrate import run as migrate
from psycopg import sql
from seed import run_seeds

INIT_DB_SH = Path(__file__).resolve().parent / "init_db.sh"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="confirm dropping the local database")
    args = parser.parse_args()

    if os.environ.get("APP_ENV") != "local":
        fail("reset_local only runs with APP_ENV=local")
    if not args.yes:
        fail("this deletes all local data; re-run with --yes")

    _, _, dbname = url_parts(database_url())
    with connect(admin_url(), autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(dbname)))
    log(f"dropped database {dbname}")

    subprocess.run([str(INIT_DB_SH)], check=True)
    migrate("up")
    run_seeds()


if __name__ == "__main__":
    main()
