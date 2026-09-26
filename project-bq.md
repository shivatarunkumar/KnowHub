# KnowHub on BigQuery — Design & Status
_Living document for the BigQuery backend. Status: built, all current features · Last updated: 2026-09-26_

> KnowHub runs on **either** PostgreSQL or BigQuery, chosen by `RUN_ON` in `.env`. Files stay
> in GCS either way. [project.md](project.md) is the plan for the product and the Postgres
> app; this file covers only what is specific to running on BigQuery.

## 1. The switch

```
RUN_ON=PSQL   →  backend/     (FastAPI on Postgres, DATABASE_URL)        make db-init, make api
RUN_ON=BQ     →  backend-bq/  (FastAPI on BigQuery, BQ_DB_* dataset)     make setup-bq, make api
```

- **One setting.** `make api` reads `RUN_ON` and starts the matching API on the same port
  (`make api-psql` / `make api-bq` start one explicitly). The web app doesn't change: it
  talks to `/api/v1` and cannot tell which API answered.
- **Same endpoints, enforced.** Both APIs expose identical paths, parameters, request bodies,
  responses and error shapes. `backend-bq/tests/test_contract.py` compares their OpenAPI
  specs and fails on any difference, so a feature can't ship on one backend only.
- **The databases are independent.** Nothing is copied between them; each starts with the
  same seed topics and teams.
- **Every feature exists on both.** New work is built twice: once in `backend/`, once in
  `backend-bq/`.

| Setting | Default | Meaning |
|---|---|---|
| `RUN_ON` | `PSQL` | `PSQL` or `BQ` (`postgres`, `bigquery` and any case also accepted) |
| `BQ_DB_PROJECT` | empty → `GCP_PROJECT_ID` | project that owns the dataset (`bigquerytarun`) |
| `BQ_DB_DATASET` | `knowhub` | dataset holding the app tables |
| `BQ_DB_LOCATION` | `europe-west2` | dataset location, next to the bucket. Fixed once created |

These are separate from `BQ_DATASET` / `BQ_LOCATION`, which name the future analytics sink
(project.md §3.7), not the application database.

## 2. Setting it up

```bash
gcloud auth application-default login      # credentials, as for GCS
make install                                # adds google-cloud-bigquery
make setup-bq                               # dataset + 27 tables + seeds (idempotent)
# RUN_ON=BQ in .env, then:
make api                                    # and make web, as usual
```

`make setup-bq` (`infra/gcs/bq/setup_bq.py`) needs Terraform ≥ 1.5 and does, in order:
1. `terraform init` (provider pinned by the committed `.terraform.lock.hcl`)
2. **imports** the dataset and any table that exists in BigQuery but not in the local state
3. `terraform apply`
4. seeds topics and teams with a `MERGE` by slug

`make setup-bq ARGS=--plan` shows the changes without applying them, and `ARGS=--no-seed`
skips the seeds.

**State is local and git-ignored** (`infra/gcs/bq/terraform.tfstate`). Step 2 is why that's
safe: on a new machine, or after the state file is lost, the script imports what already
exists before applying, so it never fails with "Already Exists" and never duplicates
anything. Checked by moving the state away and re-running: 28 resources imported,
nothing replaced.

## 3. Layout

```
infra/gcs/bq/
  main.tf                 dataset + one google_bigquery_table per tables/*.json (for_each)
  tables/<name>.json      one file per table: description, primary_key, clustering,
                          optional time_partitioning, schema (standard BigQuery field JSON)
  setup_bq.py             make setup-bq: init → import existing → apply → seed
  .terraform.lock.hcl     provider versions (committed)
backend-bq/
  app_bq/core/bq.py       the data layer (what the services use instead of a SQLAlchemy session)
  app_bq/api/deps.py      signed-in user from the cookie, with a 30 s cache
  app_bq/api/v1/*.py      routers: the same files and endpoints as backend/app/api/v1
  app_bq/services/*.py    auth, video, engagement, ai_assist, health on BigQuery
  tests/                  contract, table parity, data layer (offline); live API (make test-bq)
```

**Shared with `backend/`, not copied:** config, security (argon2, JWT), logging, middleware,
the GCS, Pub/Sub and AI adapters, the Pydantic schemas, the prompts, and the pure rules
(validation, handle generation, `@mention` parsing, prompt cleaning). `backend-bq` imports
them from `app.*` (`PYTHONPATH=.:../backend`). Only the routers and the data access are
BigQuery-specific.

## 4. Tables

The 27 tables in `infra/gcs/bq/tables` mirror the Postgres migrations column for column.
`backend-bq/tests/test_tables.py` parses the migrations and checks every table, column,
type and NOT NULL, so a new migration without a matching JSON change fails the tests.

| Postgres | BigQuery |
|---|---|
| `uuid`, `text`, `inet` | `STRING` (UUIDs come back as `uuid.UUID`) |
| `timestamptz` | `TIMESTAMP` |
| `integer`, `bigint`, `smallint` | `INT64` |
| `boolean` | `BOOL` |
| `jsonb NOT NULL DEFAULT '{}'` | `JSON REQUIRED DEFAULT JSON '{}'` |
| `vector(768)` | `REPEATED FLOAT64` (for `VECTOR_SEARCH` later) |
| `DEFAULT gen_random_uuid()` / `now()` | `defaultValueExpression`: `GENERATE_UUID()` / `CURRENT_TIMESTAMP()` |
| primary key | declared, **not enforced** (BigQuery never enforces keys) |
| foreign keys, CHECKs, unique indexes | enforced by the API (see §5) |
| `updated_at` trigger | the data layer sets `updated_at` on every `update()` |

**What is different, on purpose:**

| Postgres column | On BigQuery | Why |
|---|---|---|
| `videos.view_count` | counted from `analytics_events` (`video_view` rows) | see "Counts" below |
| `videos.like_count` | counted from `video_reactions` | |
| `videos.comment_count` | counted from `comments` | |
| `comments.like_count` | counted from `comment_reactions` | |
| `users.subscriber_count` | will be counted from `channel_subscriptions` | |
| `videos.search_vector` | not stored; search (Phase 4) will use a BigQuery search index | |
| `analytics_events.id` (bigint identity) | `STRING` UUID | BigQuery has no sequences |

Tables are clustered on the column they're looked up by (`id`, `video_id`, `user_id`,
`token_hash`, `slug`). The append-only logs are partitioned: `analytics_events` by day,
`upload_events` and `ai_requests` by month.

## 5. How the BigQuery API works

**The data layer (`app_bq/core/bq.py`)**
- Queries are written with table placeholders and named parameters:
  `SELECT * FROM {users} WHERE email = @email`. `{users}` becomes
  `` `project.dataset.users` ``, and an unknown name is an error rather than a typo that runs.
- `insert()` and `update()` type every parameter from the table's JSON schema, so NULLs,
  JSON and arrays are correct without the caller spelling out types.
- Reads use `JOB_CREATION_OPTIONAL` (no job is created for short queries). That's most of the
  difference between 300 ms and 1 s+.
- Writes are DML statements, **never streaming inserts**: streamed rows can't be updated or
  deleted for about 30 minutes, and nearly every table here gets updated.
- `db.batch()` collects a request's writes. On `commit()`, consecutive inserts into one table
  become a single multi-row `INSERT`; statements on the same table run in order (delete old
  links, then insert new ones); different tables run **in parallel**.
- Conflicts from concurrent updates ("could not serialize access") are retried with backoff.
- At `LOG_LEVEL=DEBUG` every query is logged with its time, rows and bytes scanned, like
  the SQL trace on Postgres. Anything over 3 s is logged at INFO.

**No transactions, deliberately.** A BigQuery multi-statement transaction costs 5–6 s
however small it is. We measured it: sign-in took 6.2 s with one and 2.2 s without. Each
statement is atomic on its own, and no two tables have to change together (there are no
foreign keys to violate). The worst case is a partial write, such as a video row whose
audit event is missing, never a broken invariant.

**Uniqueness without unique indexes**
- Registration inserts with `INSERT … SELECT … WHERE NOT EXISTS (same email or handle)` and
  reads the affected-row count. 0 means taken, and the API says which.
- Likes use a `MERGE` (insert or update), so double clicks can't create two rows.
- Refresh-token rotation is one `MERGE`: it revokes the old token and inserts the new one in
  one statement, since two statements on one table would run back to back at ~2 s each.
  Reuse of a revoked token still signs the user out everywhere.
- Seeds are `MERGE`d by slug.

**Counts are computed, not stored.** BigQuery runs only a couple of `UPDATE`s on a table at
once, so a `like_count` that everyone increments would conflict under load. Appending a row
never conflicts. The feed and watch queries count likes, comments and views in the same
query (with CTEs scoped to the requested videos). Views are one `analytics_events` row per
view, which the analytics phase can use directly.

**Caching round trips**
- The signed-in user is cached for 30 s per process, and dropped as soon as this API changes
  their row (login, password reset, first upload setting their team).
- The player makes many range requests per video. `media_paths` caches where a video's file
  and thumbnail are, per viewer, for 30 s. A feed or channel listing pre-fills it for every
  card, so a grid of thumbnails costs no extra queries. Editing or deleting a video clears it.

## 6. Performance (measured, 2026-09-26, europe-west2)

| Request | BigQuery | Notes |
|---|---|---|
| Topics, teams, feed, watch page, comments | 0.3–0.7 s | one query each (watch runs three in parallel) |
| Stream / thumbnail | ~0.1 s | cached after the first request |
| Sign in, refresh, like, comment, view, share | 1.7–2.7 s | one or two DML statements (~1.5–2 s each) |
| Register | 3.5–5 s | handle lookup, guarded insert, then the token |
| Edit a video, changing everything | up to ~10 s | six tables at once; BigQuery queues the DML |

Postgres answers all of these in milliseconds. BigQuery is built for analytics, not for
serving an app, and ~1.5–2 s per DML statement is its floor. Reads are fine; writes are
noticeably slow. That's the trade-off of `RUN_ON=BQ`.

**Cost:** on-demand pricing bills every query at least 10 MB, so ten thousand requests come to
about 100 GB, well under a dollar. The actual bytes scanned are in the KB range thanks to
clustering (logged at DEBUG).

## 7. Changing the schema

- **Add a table:** a Postgres migration, plus `infra/gcs/bq/tables/<name>.json`, then
  `make setup-bq`. Terraform picks up the new file automatically.
- **Add a column:** a migration, plus the field in the JSON file, then `make setup-bq`.
  Adding a NULLABLE column, or relaxing REQUIRED to NULLABLE, is an in-place change.
- **Tighten a column** (NULLABLE → REQUIRED, or a type change): BigQuery can't do this in
  place, so Terraform plans a **replacement**, which `deletion_protection = true` blocks.
  On a dataset with real data, copy it into a new table instead. On a throwaway one, drop
  the table and re-run `make setup-bq`.
- `make test` fails until the JSON matches the migration (`test_tables.py`).

## 8. Tests

| Suite | Runs in | What it checks |
|---|---|---|
| `test_contract.py` | `make test` | both APIs have the same endpoints, parameters, bodies, responses |
| `test_tables.py` | `make test` | every Postgres table/column/type/NOT NULL is mirrored in `tables/*.json` |
| `test_bq_layer.py` | `make test` | SQL expansion, typed parameters, batching and ordering, `updated_at`, defaults |
| `test_api_bq.py` | `make test-bq` | real sessions against real BigQuery: accounts, token reuse, upload, feed filters, streaming, counts, comments, sharing, restricted videos, channel, delete |

`make test-bq` creates a throwaway dataset `knowhub_test_<random>` from the same JSON files,
seeds it, runs the tests and drops it (it also expires after a day as a safety net). It
takes about a minute.

## 9. Not covered yet

- **Docker:** `docker compose` still runs the Postgres API. `RUN_ON=BQ` is the host setup
  (`make api`) only.
- **Search (Phase 4)** will need a BigQuery search index on `videos(title, description)`,
  created by the setup script, since Terraform's table resource can't manage one.
- **Notifications UI, workers, playlists, Studio:** when they're built, they're built on
  both backends (§1).
- **Faster writes for append-only events** (`analytics_events`): the Storage Write API
  would drop a view from ~2 s to ~0.3 s. Those rows are never updated, so the streaming
  restriction wouldn't matter.

## 10. Decisions

| # | Decision | Why |
|---|---|---|
| B1 | A separate API in `backend-bq/` with the same endpoints, chosen by `RUN_ON` | asked for; the contract test keeps them identical |
| B2 | `backend-bq` imports non-database code from `backend/` | one copy of the rules, prompts, schemas and adapters, so they can't drift |
| B3 | Dataset `bigquerytarun.knowhub` in `europe-west2` | next to the `knowhub-data` bucket |
| B4 | Tables as JSON files + one Terraform file in `infra/gcs/bq`; local, git-ignored state | asked for; the setup script imports existing resources, so any machine works |
| B5 | The two databases are independent; no data is copied | asked for |
| B6 | Counts computed on read, not stored | no hot-row update conflicts; appends never conflict |
| B7 | No multi-statement transactions; parallel per-table writes instead | a transaction costs 5–6 s; each statement is atomic |
| B8 | DML only, never streaming inserts | streamed rows can't be updated or deleted for ~30 minutes |
| B9 | Seeds read from the Postgres seed files | one list of topics and teams for both databases |
