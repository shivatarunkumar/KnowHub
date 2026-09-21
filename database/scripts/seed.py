"""Load seed data: seeds/common/*.sql, then seeds/<APP_ENV>/*.sql, in filename order.

Seed files must be idempotent (INSERT ... ON CONFLICT ...), because they run on
every bootstrap.

    python database/scripts/seed.py
"""

from __future__ import annotations

import os

from _db import SEEDS_DIR, connect, database_url, log


def seed_files(app_env: str) -> list:
    files = []
    for folder in ("common", app_env):
        directory = SEEDS_DIR / folder
        if directory.is_dir():
            files.extend(sorted(directory.glob("*.sql")))
    return files


def run_seeds(url: str | None = None) -> None:
    app_env = os.environ.get("APP_ENV", "local")
    files = seed_files(app_env)
    with connect(url or database_url()) as conn:
        for path in files:
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
            log(f"seeded {path.parent.name}/{path.name}")
    log(f"seeds done ({len(files)} files, APP_ENV={app_env})")


if __name__ == "__main__":
    run_seeds()
