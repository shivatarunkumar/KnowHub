# KnowHub

KnowHub — short for **Knowledge Hub** — is an internal video platform for engineering
knowledge: bug fixes, incident resolutions, how-tos and reusable work, shared as videos and
shorts instead of being re-solved from scratch. Browsing, watching, commenting and subscribing
work the way people already expect, in our own colours.

Everything runs on a laptop today — Postgres, the API, the web app, file storage and the
AI writing assist. GCP deployment is a config switch, not a rewrite (§3.8 of
[project.md](project.md)).

**The plan, architecture, data model and roadmap live in [project.md](project.md)** — that
file is the single source of truth. This README is only about running the thing.

## What works today

| Area | What you can do |
|---|---|
| **Accounts** | Register, sign in, stay signed in (argon2id passwords, JWT access token + rotating refresh token in httpOnly cookies) |
| **Watch** | Browse the home feed, filter by topic, watch with seeking (HTTP range requests), see views, likes and comments — all without signing in |
| **Upload** | Drag and drop, fill in the details while the file uploads straight to storage in 8 MB chunks (so size is not limited by the API), pick the poster frame, publish |
| **Write with AI** | "Improve with AI" on the title, the description and comments — a local Ollama model rewrites your own words and never invents facts |
| **Resources** | Attach Confluence/repo/PR/ticket links and copy-ready code snippets, so viewers don't retype what's on screen |
| **Engagement** | Like, dislike, comment with one level of replies, like comments, edit your comment for a minute, `@mention` colleagues, share inside KnowHub (no Slack, no email) |
| **Your channel** | `/channel/{handle}`: your uploads with a Manage dialog per video — edit the wording, change who can watch (everyone / link only / specific people / only you), turn comments off, or delete it |
| **Audit** | Every upload and every later change is appended to `upload_events` |
| **About page** | `/about` explains the project and diagrams the upload, login and engagement flows for anyone opening KnowHub for the first time |

Not built yet: transcoding to HLS, the in-browser trim/crop editor, search, the shorts feed,
subscriptions and the notification bell (notifications are stored, but there is no UI yet),
playlists and history, Studio analytics, semantic search, GCP deployment. See the roadmap
in [project.md §8](project.md).

## Run it locally

What you need: **Python 3.12+**, **Node 20+**, **PostgreSQL 16 or newer** with `pg_trgm`
and `pgvector` (we run 17), and **psql** on your PATH. `make check` tells you what's missing.
[Ollama](https://ollama.com) is optional — without it everything works except the AI
writing assist.

```bash
cp .env.example .env     # then set DATABASE_URL / POSTGRES_ADMIN_URL to your Postgres
make install             # .venv for the backend + npm packages for the frontend
make db-init             # creates the database, role, tables and seed topics
make api                 # http://localhost:8000  (leave it running)
make web                 # http://localhost:3000  (in a second terminal)
```

`make db-init` is idempotent: it runs `init_db.sql` (role, database, privileges,
extensions), then every pending migration, then the seeds, and it logs each step. Re-run it
as often as you like. `make db-reset` drops the database and rebuilds it from scratch.

| | URL |
|---|---|
| Web app | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Health of every dependency | http://localhost:8000/api/v1/health |

**Storage and AI.** Video files go to a GCS bucket (`GCS_BUCKET`, `knowhub-data` by
default) under `raw/users/{user_id}/…` and `media/videos/{video_id}/…`. Locally you can
point `GCS_ENDPOINT_URL` at the fake-gcs-server container instead, or use the real bucket
with your own `gcloud auth application-default login` credentials — no service-account key
is needed. The AI assist calls Ollama at `OLLAMA_BASE_URL` (`llama3.2`); set
`AI_PROVIDER=none` to switch it off.

### Set up a second machine

`.env` is deliberately not in git (it holds your own database password and project), so a
fresh clone starts from `.env.example`, whose defaults describe the **Docker** setup. For
the host setup you must change six things:

| Key | Set it to |
|---|---|
| `JWT_SECRET` | a fresh random value: `openssl rand -hex 32`. It is per-machine — never copy it between machines or into git |
| `DATABASE_URL` | your local Postgres, e.g. `postgresql+asyncpg://tarun:12345@localhost:5432/knowhub` |
| `POSTGRES_ADMIN_URL` | a superuser on the same server, e.g. `postgresql://postgres@localhost:5432/postgres` — `make db-init` uses it to create the role and database |
| `GCP_PROJECT_ID` | the project that owns the bucket and the Pub/Sub topics (not `knowhub-local`) |
| `GCS_ENDPOINT_URL` | **empty** — an empty value means real GCS; set it only for the emulator |
| `PUBSUB_EMULATOR_HOST` | **empty**, for the same reason |

Then authenticate to GCP once (no service-account key needed) and set up the database:

```bash
gcloud auth application-default login
gcloud config set project <your-project>
make db-init
```

### Check the connections before starting anything

```bash
make check-db     # Postgres: reachable, role, database, extensions, migrations, seeds
make check-gcp    # GCP: config, network, credentials, bucket read/write, topics
make check-all    # the two above, plus the tool check
```

Each prints one line per check and, when something fails, the command that fixes it:

```
[check-gcp] checking configuration, credentials, bucket and Pub/Sub

  ok    config         project=my-project bucket=knowhub-data
  ok    network        reached oauth2.googleapis.com, storage.googleapis.com, … on 443
  FAIL  credentials    no Application Default Credentials on this machine
                       → run: gcloud auth application-default login
```

They exit non-zero on failure, so you can chain them in a script. `check-gcp` uploads and
deletes a small probe object to prove writes work; `--no-write` skips that.

**If the API answers 503 on `/api/v1/health`,** that is the app telling you a *required*
dependency is unreachable — it is not a crash. The body names the failing check, but it
only reports a timeout; `make check-db` / `make check-gcp` tell you *why*:

- `database` not ok → Postgres isn't running, `DATABASE_URL` is wrong, or `make db-init` hasn't been run
- `storage` / `pubsub` timing out → almost always no Application Default Credentials, or a firewall/proxy between you and `*.googleapis.com`
- `ai` not ok → Ollama isn't running, or the models aren't pulled (`ollama pull llama3.2`). This one only makes the status `degraded`; everything except the writing assist still works, and `AI_PROVIDER=none` silences it

### Or run the whole stack in Docker

```bash
./scripts/bootstrap.sh
```

One command: it writes `.env`, starts Postgres, fake-gcs-server and the Pub/Sub emulator,
creates the database, buckets and topics, pulls the AI models, and starts the API and web
app. Useful on a machine where you'd rather not install Postgres.

## Everyday commands

`make help` lists them all.

| Command | What it does |
|---|---|
| `make check` | verify python3, node, npm and psql are installed |
| `make check-db` / `make check-gcp` / `make check-all` | verify the database and GCP connections without starting the API |
| `make install` | install every dependency (backend, database/infra tools, frontend) |
| `make db-init` / `make db-reset` | create or rebuild the database |
| `make db-status` / `make db-shell` | list migrations / open psql |
| `make api` / `make web` | run the API / the web app |
| `make test` | backend + database tests and the frontend type check |
| `make lint` | ruff lint and format check |
| `make up` / `make down` / `make logs` | the Docker stack |
| `make provision` | create buckets, Pub/Sub topics and subscriptions, AI models |
| `make clean` | remove `.venv`, `node_modules` and build output |

## How it fits together

```
Browser ──▶ Next.js (web)  ──▶ FastAPI (api) ──▶ PostgreSQL   metadata, engagement, audit
   │                                          ├─▶ GCS         video files, thumbnails
   │                                          ├─▶ Ollama      writing assist
   └──────── 8 MB chunks ────▶ GCS            └─▶ Pub/Sub     events (workers come later)
```

The browser uploads directly to storage with a resumable session, so video bytes never pass
through the API. Playback streams back through `GET /videos/{id}/stream`, which honours
range requests. Every external service sits behind an adapter
(`backend/app/adapters/`), picked by a config switch, so the local and GCP setups run the
same code.

## Repository layout

| Path | Contents |
|---|---|
| `project.md` | the plan: product, architecture, data model, API, roadmap |
| `frontend/` | Next.js app (App Router, Tailwind v4): `/`, `/watch/[id]`, `/upload`, `/channel/[handle]`, `/login`, `/register` |
| `backend/` | FastAPI app. Every setting is in `backend/app/core/config.py` |
| `database/` | `init_db.sql`, migrations, seeds and the setup script ([README](database/README.md)) |
| `infra/` | provisioning scripts and the [inventory of GCP resources](infra/GCP_RESOURCES.md) ([README](infra/README.md)) |
| `scripts/` | `bootstrap.sh` (Docker setup), `localenv.sh` (loads `.env` for host commands) |
| `.env.example` | every configuration key, documented |

## Tests

```bash
make test   # 65 backend tests, 10 database tests, frontend type check
make lint
```

The backend tests that need a database create and remove their own users and videos, and
skip themselves when Postgres isn't reachable.
