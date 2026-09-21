# database/

All KnowHub database work lives here: Postgres migrations (DDL), seed data, and the scripts that apply them. Later phases add BigQuery DDL and queries under `bigquery/`. The backend only *uses* the schema; it never creates it.

## Layout
```
postgres/
  init_db.sql   FIRST script: creates the role, database, privileges and extensions
  migrations/   V<NNN>__<name>.sql: the only way the schema changes (forward-only)
  seeds/
    common/     seed data for every environment (idempotent)
    local/      local-only seed data (demo users, sample videos: later phases)
  schema/       schema.sql: generated snapshot for reading/review (don't edit)
scripts/
  init_db.sh      run init_db.sql with the values from DATABASE_URL
  migrate.py      apply pending migrations (`up`) or show `status`
  seed.py         run seeds/common then seeds/$APP_ENV
  reset_local.py  drop + recreate + migrate + seed (APP_ENV=local only, needs --yes)
  dump_schema.sh  regenerate postgres/schema/schema.sql from the compose Postgres
tests/            migration runner tests
```

## How to run the scripts

### The one command (recommended)
```bash
python database/scripts/setup_db.py
```
`setup_db.py` is the single entry point. It runs all three steps in order, skips whatever already exists, and logs each step:

| Step | What runs | As | Creates |
|---|---|---|---|
| 1 | `postgres/init_db.sql` | admin (`POSTGRES_ADMIN_URL`) | role, database, privileges, extensions |
| 2 | `postgres/migrations/V*.sql` | app user (`DATABASE_URL`) | tables, indexes, triggers |
| 3 | `postgres/seeds/**` | app user | topic list (and local demo data later) |
| 4 | verify | app user | reports tables, migrations, extensions, topics |

Useful flags:

| Flag | Effect |
|---|---|
| `--skip-seed` | schema only, no data |
| `--reset --yes` | DROP the database first, then rebuild it (only when `APP_ENV=local`) |
| `--database-url`, `--admin-url` | use a different database than `.env` |
| `--wait 60` | wait longer for a server that is still starting |
| `-v` | verbose: show every statement's output |

Example run:
```
10:51:12  INFO    KnowHub database setup → tarun@localhost/knowhub
10:51:12  INFO    server: PostgreSQL 16.13 (Homebrew)
10:51:12  INFO    running init_db.sql (role tarun, database knowhub)
10:51:13  INFO    step 1/3 done: role, database, privileges and extensions are in place
10:51:13  INFO    applying migrations from database/postgres/migrations
10:51:13  INFO    step 2/3 done: 0 of 9 migration files were already applied before this run
10:51:13  INFO    step 3/3 done: seed data is up to date
10:51:13  INFO    verify: database=knowhub tables=22 migrations=9 (latest V009) extensions=pg_trgm, vector topics=12
```

Where it runs:
- **on your machine**: needs Python with `psycopg` and `psql` on the PATH. Hostnames like `host.docker.internal` in `.env` are switched to `localhost` automatically.
- **in docker** (no local Python needed): `make setup-db`, or `docker compose run --rm init python database/scripts/setup_db.py`.
- **whole app**: `./scripts/bootstrap.sh` and `docker compose up` run the same steps through the `init` service.

### Running a single step
```bash
bash   database/scripts/init_db.sh        # 1. role + database + privileges + extensions
python database/scripts/migrate.py up     # 2. tables
python database/scripts/seed.py           # 3. seed data
```

Or with the Make targets, which run inside the `init` container so the host needs only Docker:

| Command | What it does |
|---|---|
| `make setup-db` | everything: init_db.sql + migrations + seeds |
| `make migrate` | apply pending migrations |
| `make migrate-status` | list applied / pending migrations |
| `make seed` | re-run seeds |
| `make reset-local` | wipe and rebuild the local database |
| `make dump-schema` | refresh `postgres/schema/schema.sql` |

Settings come from `.env`:
- `POSTGRES_ADMIN_URL`: superuser, used only by `init_db.sh` and `reset_local.py`
- `DATABASE_URL`: the app role, password and database; `init_db.sql` creates them from this URL
- `APP_ENV`: selects the seed folder
- `DB_EXTENSIONS`: legacy override; `init_db.sql` creates `pg_trgm`, plus `vector` when the server has it

## Adding a schema change
1. Create the next file, e.g. `postgres/migrations/V004__videos.sql`. Use lowercase snake_case names.
2. `make migrate`, then `make dump-schema`, and commit both.
3. Never edit a migration that has been applied anywhere. The runner stores a checksum per file and refuses to run if an applied file changes. Fix mistakes with a new migration.
4. Each file runs in one transaction. For statements that can't run in a transaction (e.g. `CREATE INDEX CONCURRENTLY`), make the first line `-- migrate:no-transaction`.

Conventions: `uuid` primary keys (`gen_random_uuid()`), `timestamptz` timestamps, `created_at`/`updated_at` on mutable tables with the `set_updated_at()` trigger (V001), and `text` + `CHECK` instead of enum types (easier to evolve).

## Tests
`make test` runs `database/tests`. The integration tests create and drop a throwaway database when `TEST_POSTGRES_ADMIN_URL` is set (the Make target sets it to the compose Postgres).
