"""Migration runner tests.

Unit tests always run. Integration tests run when TEST_POSTGRES_ADMIN_URL points at a
server where a throwaway database can be created (e.g. the compose Postgres).
"""

import os
import shutil
import uuid

import psycopg
import pytest
from _db import MIGRATIONS_DIR
from migrate import MigrationError, load_migrations, plan, run
from psycopg import sql


def write(directory, name, body="SELECT 1;"):
    (directory / name).write_text(body)


def test_repo_migrations_load_in_order():
    migrations = load_migrations(MIGRATIONS_DIR)
    versions = [m.version for m in migrations]
    assert versions == sorted(versions)
    assert versions[:3] == [1, 2, 3]


def test_rejects_missing_directory(tmp_path):
    with pytest.raises(MigrationError, match="directory not found"):
        load_migrations(tmp_path / "nope")


def test_rejects_bad_filename(tmp_path):
    write(tmp_path, "001_create_users.sql")
    with pytest.raises(MigrationError, match="bad migration filename"):
        load_migrations(tmp_path)


def test_rejects_duplicate_versions(tmp_path):
    write(tmp_path, "V001__a.sql")
    write(tmp_path, "V0001__b.sql")
    with pytest.raises(MigrationError, match="duplicate migration version 1"):
        load_migrations(tmp_path)


def test_plan_returns_pending(tmp_path):
    write(tmp_path, "V001__a.sql")
    write(tmp_path, "V002__b.sql")
    migrations = load_migrations(tmp_path)
    applied = {1: ("a", migrations[0].checksum)}
    assert [m.version for m in plan(migrations, applied)] == [2]


def test_plan_detects_edited_migration(tmp_path):
    write(tmp_path, "V001__a.sql")
    migrations = load_migrations(tmp_path)
    with pytest.raises(MigrationError, match="edited after it was applied"):
        plan(migrations, {1: ("a", "not-the-checksum")})


def test_plan_detects_missing_file(tmp_path):
    with pytest.raises(MigrationError, match="file is missing"):
        plan([], {1: ("a", "x")})


def test_plan_rejects_out_of_order_pending(tmp_path):
    write(tmp_path, "V001__a.sql")
    write(tmp_path, "V002__b.sql")
    write(tmp_path, "V003__c.sql")
    migrations = load_migrations(tmp_path)
    applied = {1: ("a", migrations[0].checksum), 3: ("c", migrations[2].checksum)}
    with pytest.raises(MigrationError, match="older than the latest applied"):
        plan(migrations, applied)


ADMIN_URL = os.environ.get("TEST_POSTGRES_ADMIN_URL")


@pytest.fixture
def scratch_db():
    if not ADMIN_URL:
        pytest.skip("TEST_POSTGRES_ADMIN_URL not set")
    name = f"knowhub_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = ADMIN_URL.rsplit("/", 1)[0] + f"/{name}"
    try:
        yield url
    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.mark.integration
def test_repo_migrations_apply_and_are_idempotent(scratch_db):
    run("up", url=scratch_db)
    run("up", url=scratch_db)  # second run is a no-op
    with psycopg.connect(scratch_db) as conn:
        count = conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
        tables = {r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")}
    assert count == len(load_migrations(MIGRATIONS_DIR))
    assert {"users", "refresh_tokens", "topics"} <= tables


@pytest.mark.integration
def test_edited_migration_fails_run(scratch_db, tmp_path):
    for path in MIGRATIONS_DIR.glob("*.sql"):
        shutil.copy(path, tmp_path / path.name)
    run("up", tmp_path, url=scratch_db)
    first = sorted(tmp_path.glob("V001__*.sql"))[0]
    first.write_text(first.read_text() + "\n-- edited\n")
    with pytest.raises(MigrationError, match="edited after it was applied"):
        run("up", tmp_path, url=scratch_db)
