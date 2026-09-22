# KnowHub — Project Plan & Architecture
_Living document. Status: v0.5 · Phases 0–3 built, Phase 5 mostly built · Last updated: 2026-09-21_

> **Current target: run everything locally.** Every feature (auth, upload, playback, search, engagement, notifications, AI writing help) must work on a laptop, set up by scripts with no manual steps: `make install` → `make db-init` → `make api` + `make web` on the host, or `./scripts/bootstrap.sh` for the full Docker stack. GCP deployment comes later and is a config switch, not a rewrite. See §1.1, §3.7, §3.8 and §3.10.

## 1. Overview
KnowHub — the name is short for **Knowledge Hub** — is an internal video and shorts platform for engineering knowledge, built the way people already expect a video site to work. Engineers upload videos and shorts that explain bug fixes, incident resolutions, how-tos and reusable work. Anyone in the company can come and search for "how did we fix X?" and watch the answer.

**Goals**
- Make it quick to find and watch an existing resolution before re-solving a problem.
- Make it easy to record and upload a fix with rich context (topic, incident, ticket, repo).
- Tell people when new content appears on topics they care about (e.g. BigQuery, Pub/Sub).
- Feel familiar: the interactions people already know from any video site, with our own fonts and colors — a deep forest green with warm cream surfaces, Source Serif 4 for display type and Figtree for everything else. Colours are tokens in `globals.css`; no component names a colour.

**Access model**
| Action | Anonymous | Logged in |
|---|---|---|
| Browse home, search, watch videos & shorts, view comments | ✅ | ✅ |
| Upload video/short, like, comment, subscribe, playlists, history, notifications | ❌ (prompt login) | ✅ |
| Edit/delete own videos, Studio dashboard | ❌ | ✅ (owner) |
| Manage topics, moderate content | ❌ | ✅ (admin role) |

> "Anonymous" still means inside the company network. See Open Questions (IAP/VPN).

> ⚙️ = a recommendation that hasn't been confirmed yet. Change it if you prefer something else.

### 1.1 Build status (what actually runs today)
Everything below runs locally: `make install` → `make db-init` → `make api` + `make web`.
See the [README](README.md) for the commands and the [roadmap](#8-implementation-roadmap)
for what each phase covers.

| Phase | State | What is in the code |
|---|---|---|
| **0. Foundations** | ✅ built | Monorepo, `config.py` + `.env.example` (every key in one place), adapters for storage/events/AI, docker-compose with emulators, `database/` (init_db.sql, 13 migrations, seeds, one setup script), `infra/scripts/provision.py`, Makefile, CI |
| **1. Auth & users** ✅ built | ✅ built | `users` + `refresh_tokens`, argon2id, JWT access token + rotating refresh token in httpOnly cookies, lockout after 5 failed logins, reuse detection, register/login UI, account menu |
| **2. Upload** | ✅ built | Resumable chunked upload straight from the browser to GCS (8 MB chunks, retries), per-user folders, metadata, optional links and code snippets, poster frame captured in the browser, `upload_events` audit, AI writing assist on title/description |
| **2b. Video editor** | ⬜ not started | `video_edits` table exists; the trim/crop UI and the worker do not |
| **3. Watch & home** ✅ built | ✅ built | Home feed with topic chips, watch page with range-request streaming, drawn covers when a video has no thumbnail, "Up next" sidebar, channel pages with owner controls (§2.5) |
| **4. Search** | ⬜ not started | `search_vector` and trigram indexes are in the schema; no endpoint or UI yet |
| **5. Engagement** 🟨 mostly built | 🟨 mostly built | Likes/dislikes, comments + one level of replies, comment likes, 60-second edit window, `@mentions`, in-app share + "shared with me" API, view counts. Missing: playlists, watch later, history UI |
| **6. Subscriptions & notifications** | 🟨 storage only | `topic_subscriptions`, `channel_subscriptions` and `notifications` are written to (shares, replies, mentions), but there is no bell, no feed and no worker |
| **7. Shorts** | ⬜ not started | `type='short'` is stored and badged; no vertical feed |
| **8. Studio & analytics** | ⬜ not started | `analytics_events` table exists; no dashboard |
| **9–11. Semantic search, GCP deploy, more AI** | ⬜ not started | `video_embeddings` (pgvector, HNSW) and the BigQuery DDL are written but unused |

**API surface today** (`/api/v1`, full list at http://localhost:8000/docs):
`auth/{register,login,refresh,logout,me,forgot-password,reset-password}` · `topics` · `teams` · `videos/feed` ·
`videos/uploads/start` + `videos/{id}/complete` · `videos/{id}` (GET/PATCH/DELETE) ·
`videos/{id}/stream` · `videos/{id}/thumbnail` (GET/POST) · `videos/{id}/view` ·
`videos/{id}/reaction` · `videos/{id}/comments` · `comments/{id}` (PATCH/DELETE) ·
`comments/{id}/reaction` · `videos/{id}/share` · `shared-with-me` · `users/search` ·
`channels/{handle}` · `ai/enhance` + `ai/enhance/outcome` · `health`

**Web routes today**: `/` · `/watch/[id]` · `/upload` · `/channel/[handle]` · `/about` · `/login` · `/register` · `/forgot-password` · `/reset-password`

`/about` is the in-app explainer: what KnowHub is, why it exists, and diagrams of the architecture, the upload path into Cloud Storage, the login flow and the engagement tables. It is written from this document and must be updated with it.

**Tests**: 65 backend, 10 database, plus the frontend type check (`make test`).

**Connection checks**: `make check-db` and `make check-gcp` verify Postgres and GCP
(config → network → credentials → bucket read/write → topics) outside the API, each check
printing the command that fixes it. `/api/v1/health` reports the same dependencies at
runtime but can only say "timed out"; these say why.

## 2. Features (what people expect from a video platform, adapted)

### 2.1 Viewing
- **Home feed**: grid of video cards (thumbnail, duration, title, uploader, views, age). New and anonymous visitors see *Latest + Trending*. Logged-in users also see *From your subscriptions* and *Recommended for your topics*.
- **Topic chips bar** across the top of home (All, BigQuery, Pub/Sub, GKE, Cloud SQL, …), and a
  **team filter** beside it (All teams by default, grouped by division). Topics say what a video
  is about, teams say who it came from, and the two combine.
- **Watch page**: adaptive HLS player (quality selector, speed, captions later, theater/fullscreen, keyboard shortcuts, resume position). Below the player: title, view count, like/dislike, share, save, subscribe, description with links (incident, Jira, repo, PR), and comments. Sidebar: "Up next" related videos.
- **Shorts**: vertical 9:16 full-height feed with swipe/scroll and autoplay loop. Like, comment and share buttons on the right. A Shorts shelf on home.
- **Channel page** (each user is a channel): banner, avatar, subscriber count, Videos / Shorts / Playlists tabs.
- **Search**: search bar with autocomplete. Results page with filters (type: video/short, topic, category, upload date, duration) and sort (relevance, date, views).

### 2.2 Uploading (login required)
- Upload dialog, like a creator studio. Drag and drop the file, then fill in details while it uploads.
- **Required metadata**: title, description, type (Video / Short), primary topic (GCP service, e.g. BigQuery), category (Bug fix · Incident resolution · How-to · Knowledge share · Demo · Reusable component).
- **Optional metadata**: additional topics, tags, incident ID, Jira ticket, repo/PR link, environment (prod/stage/dev), severity, custom thumbnail, visibility (Public-internal / Unlisted / Private / Draft), and more fields to come.
- **✂️ Edit the video while it uploads** (a basic creator-studio editor). The upload runs in the background while the user previews the video from the local file and edits it:
  - **v1 (core):**
    - **Keep only the wanted time range(s):** drag start/end handles on a timeline to trim, and cut out unwanted segments in the middle (e.g. a password shown on screen, dead time). Multiple ranges can be kept and are joined in order.
    - **Crop the frame:** drag a crop box over the video (free or fixed ratio: 16:9, 9:16 for shorts, 1:1), e.g. to focus on one terminal window or hide a sidebar.
    - **Thumbnail:** pick a frame from the video or upload a custom image.
    - Undo/redo and a live preview of the result.
  - **Nice-to-have (later):** rotate, mute a segment, blur a region (hide secrets), captions editing, intro/outro, merge clips.
  - Edits are **non-destructive**: they're saved as an edit list, and the original file is kept.
  - Edits can also be changed **after** upload (Studio → Edit video). This re-processes the video, and the old version stays live until the new one is ready.
- **✨ AI writing assist**: "Improve with AI" buttons next to title and description. The AI can:
  - rewrite a rough description into a clear one (problem → root cause → fix → takeaways)
  - fix grammar and tone
  - suggest a better title
  - suggest topics and tags.

  The user sees a before/after preview and chooses **Accept / Edit / Discard**. Nothing is saved without the user's say-so. See §3.9.
- Progress bar, processing status ("Uploading → Processing → Ready"), and a notification when the video is ready.
- Shorts validation: vertical or square, ≤ 60s (configurable).

### 2.3 Engagement (login required)
- Like / dislike (like count shown, dislike count private).
- Comments with one level of replies, likes on comments, sort by top/newest, edit/delete own, uploader can pin.
- **Share (within KnowHub)**: share a video or short with other KnowHub users (pick users → they get an in-app notification and it appears in their "Shared with me" list), plus copy link / share at timestamp (`?t=123`). No external sharing (Slack/email) for now.
- Save to Watch Later and to playlists.
- Watch history (view, remove, pause).

### 2.4 Subscriptions & notifications
- **Topic subscriptions**: subscribe to a topic (e.g. BigQuery). When a video on that topic is published, subscribers get a notification.
- **Channel subscriptions**: subscribe to an uploader.
- Notification bell with unread count and a list. Mark read / mark all read.
- Delivery: in-app only (bell). Notifications stay inside the application.
- Subscriptions page: feed of videos from subscribed topics and channels.

### 2.5 Your channel (built)
`/channel/{handle}` is a user's page: banner, avatar, name, @handle, video count and total views,
then their videos. Visitors see published, non-unlisted videos in the usual grid.

**The owner sees their own channel as a management list** — every upload, including the hidden
ones and the ones still processing — with a **Manage** dialog per video:
- **Wording**: title and description (both with the AI writing assist), topic, category.
- **Resources**: add, change or remove the links and code snippets shown under the video.
- **Who can watch** (one choice per video):
  | Visibility | Who can watch | Where it appears |
  |---|---|---|
  | `internal` | everyone, signed in or not | home feed, search, channel |
  | `unlisted` | anyone with the link | nowhere; link only |
  | `restricted` | only the people on the video's list (`video_viewers`) | their feed and the link |
  | `private` | the owner alone — effectively switched off | the owner's channel only |
- **Comments on/off** per video. With them off nobody can post or reply; comments already
  posted stay readable.
- **Delete**, with a confirmation. The row is soft-deleted (`deleted_at`) so the upload audit
  trail survives, and the file and thumbnail are removed from storage.

Every change is appended to `upload_events` (`edited`, `visibility_changed`, `comments_changed`,
`deleted`), so the audit trail covers the whole life of a video, not just its upload.

### 2.5b Studio (creator analytics, later)
- Basic analytics per video (views over time), powered by BigQuery.

### 2.6 AI features
**Now:** AI writing assist on upload (§2.2, §3.9).

**Future: semantic search (planned; data is prepared from day one).**
- Users search in plain language ("pubsub messages getting redelivered twice") and get relevant videos even when no keywords match.
- **Each video's title + description (plus topics/tags) is stored as an embedding** in Postgres (`pgvector`, table `video_embeddings`). Embeddings are generated when a video is published and regenerated when its title or description changes.
- Search becomes *hybrid*: keyword (Postgres full-text) + vector similarity, merged and ranked.
- The same embeddings power "Similar resolutions" / "Up next" recommendations.
- Later extensions: embed transcripts (Speech-to-Text) as well, AI summaries and chapters.

> Note: we store embeddings from the start, even before semantic search ships, so the feature launches with existing content already searchable.

## 3. Architecture

### 3.1 High-level diagram
```mermaid
flowchart LR
  U[Browser<br/>Next.js UI] -->|HTTPS| LB[Cloud Load Balancer<br/>+ Cloud CDN]
  LB --> FE[Cloud Run: web<br/>Next.js]
  LB --> API[Cloud Run: api<br/>FastAPI]
  LB -->|HLS segments, thumbnails| PUB[(GCS: knowhub-media<br/>processed)]
  API --> DB[(Cloud SQL<br/>PostgreSQL)]
  API -->|signed upload URL| U
  U -->|resumable upload| RAW[(GCS: knowhub-raw<br/>users/&lt;user_id&gt;/...)]
  RAW -->|object finalize| PS1{{Pub/Sub:<br/>video-uploaded}}
  PS1 --> W1[Cloud Run: media-worker]
  W1 -->|create job| TC[Transcoder API]
  TC -->|HLS renditions + thumbs| PUB
  TC -->|job done| PS2{{Pub/Sub:<br/>transcode-events}}
  PS2 --> W1
  W1 -->|status=READY| DB
  W1 -->|publish| PS3{{Pub/Sub:<br/>video-published}}
  PS3 --> W2[Cloud Run: notify-worker]
  W2 --> DB
  API -->|view/like events| PS4{{Pub/Sub:<br/>analytics-events}}
  PS4 -->|BigQuery subscription| BQ[(BigQuery<br/>analytics)]
  API -->|enhance text| AI[AI provider<br/>Vertex Gemini / Ollama]
  PS3 --> W3[Cloud Run: embed-worker]
  API -->|metadata changed| PS5{{Pub/Sub:<br/>video-metadata-changed}}
  PS5 --> W3
  W3 -->|embed title+description| AI
  W3 -->|upsert vectors| DB
```
_Locally, each GCP box is replaced by an emulator or local equivalent. See §3.7._

### 3.2 Components
| Component | Tech | Responsibility |
|---|---|---|
| **web** | Next.js (React, TypeScript) on Cloud Run ⚙️ | The video-site UI, SSR for home and watch pages |
| **api** | FastAPI on Cloud Run | Auth, users, videos, search, comments, likes, subscriptions, notifications, signed URLs |
| **media-worker** | Python on Cloud Run (Pub/Sub push) | Reacts to uploads: probes the file, starts Transcoder jobs, marks videos READY/FAILED |
| **notify-worker** | Python on Cloud Run (Pub/Sub push) | Sends `video-published` notifications to topic and channel subscribers, and delivers in-app shares |
| **embed-worker** | Python on Cloud Run (Pub/Sub push) | Generates and stores title+description embeddings for semantic search |
| **AI provider** | Vertex AI Gemini + text embeddings (GCP) / Ollama (local) ⚙️ | Writing assist on upload; embeddings |
| **Database** | Cloud SQL for PostgreSQL 16 | Source of truth: users, videos, engagement, subscriptions, upload audit |
| **Object storage** | GCS | Raw uploads (per-user folders) and processed HLS/thumbnails |
| **Transcoding** | GCP Transcoder API ⚙️ | Adaptive bitrate HLS (360p/720p/1080p) and thumbnail sprites |
| **Messaging** | Pub/Sub | Decouples upload → processing → notification → analytics |
| **Analytics** | BigQuery | View, watch-time and engagement events; trending and Studio stats |
| **CDN** | Cloud CDN + HTTPS LB | Fast segment delivery |
| **Secrets** | Secret Manager | DB credentials, JWT signing key |
| **Provisioning / CI** | Idempotent scripts in `database/` and `infra/` (§3.10), GitHub Actions / Cloud Build, Artifact Registry | Any machine or project set up by script |

### 3.3 Upload flow
1. The user (logged in) opens Upload and picks a file. The UI calls `POST /api/v1/uploads` with the file name, size, MIME type and type (video/short).
2. The API creates a `videos` row (`status=UPLOADING`) and an `upload_events` row. It returns a **V4 signed resumable-upload URL** for `gs://knowhub-raw/users/{user_id}/videos/{video_id}/source.{ext}`.
3. The browser uploads directly to GCS, so file bytes never pass through the API. Meanwhile the user fills in title, description, topic, etc. (`PATCH /api/v1/videos/{id}`), and **edits the video** in the in-browser editor. The preview plays from the local file via `URL.createObjectURL`, so there's no need to wait for the upload. Edits are saved as an edit list (`PUT /api/v1/videos/{id}/edits`).
4. GCS `OBJECT_FINALIZE` → Pub/Sub `video-uploaded` → media-worker sets `status=PROCESSING`. It **waits until the user clicks "Save/Publish" in the editor** (or uses the latest saved edit list), then probes the source and applies the edit list:
   - FFmpeg `trim`/`concat`/`crop`/`transpose`/volume filters locally
   - Transcoder API `editList` + crop/pad configs on GCP

   It then enforces the Shorts rules on the **edited** duration and aspect ratio, and transcodes. Output goes to `gs://knowhub-media/videos/{video_id}/v{edit_version}/hls/`, so an old version keeps playing while a re-edit processes.
5. Transcoder completion → Pub/Sub → media-worker records renditions, duration and thumbnails, and sets `status=READY`. If the user clicked Publish, it sets `published_at` and publishes `video-published`.
6. notify-worker looks up subscribers of the video's topics and uploader, then bulk-inserts `notifications`.

### 3.4 Playback flow
- The watch page calls `GET /api/v1/videos/{id}`, which returns metadata and the `hls_url` (CDN URL of `master.m3u8`).
- The player (hls.js / Video.js) streams segments from Cloud CDN.
- The player sends heartbeat events (`POST /api/v1/videos/{id}/view`, then progress events). The API increments the view counter in Postgres (debounced per user/session) and publishes the raw event to `analytics-events` → BigQuery.

### 3.5 GCS layout
```
gs://knowhub-raw/                      # private, lifecycle: move to Coldline after 30d
  users/{user_id}/
    videos/{video_id}/source.mp4
    shorts/{video_id}/source.mp4
    avatars/…  banners/…
gs://knowhub-media/                    # served via CDN
  videos/{video_id}/hls/master.m3u8, 720p/…, 360p/…
  videos/{video_id}/thumbs/default.jpg, sprite.jpg
```

### 3.6 Auth
- Email and password in the Postgres `users` table. Passwords are hashed with **argon2** (pwdlib).
- A short-lived **JWT access token** (15 min) plus a **refresh token** (14 days). The refresh token is stored hashed in `refresh_tokens`, delivered as an httpOnly cookie, and rotated on each use.
- FastAPI dependencies: `get_current_user_optional` for public endpoints (to personalize when logged in) and `get_current_user` for protected ones. A role check (`user`, `admin`).
- **Forgotten password**: `POST /auth/forgot-password` always answers the same way, whether or not the address has an account, so it cannot be used to discover who is registered. A single-use token (SHA-256 hashed, 30 min) is stored in `password_reset_tokens`; asking again invalidates the previous link. `POST /auth/reset-password` sets the password, clears any lockout, and revokes every refresh token, so all other devices are signed out.
  - **Delivery is the one piece still missing**: there is no mail server, so the link is written to the API log, and returned in the response only when `APP_ENV=local`. Wiring a provider means sending `reset_url` from that endpoint; nothing else changes.
- Later: add "Sign in with Google" (Google Workspace OIDC) that links to the same `users` row.

### 3.7 Local-first development (current target)
Two ways to run it, and both are local-first:

1. **Host setup (what we use day to day)** — Homebrew PostgreSQL 17 (`pg_trgm`, `pgvector`),
   the API and the web app straight from `make api` / `make web`, files in the real GCS
   bucket `knowhub-data` using `gcloud auth application-default login` (no service-account
   key), and Ollama on the host for the writing assist. `scripts/localenv.sh` loads `.env`
   and rewrites container hostnames to `localhost`, so the same `.env` works either way.
2. **Full Docker stack** — `./scripts/bootstrap.sh` replaces every GCP service with an
   emulator behind the same adapter interfaces, so the code paths match.

The table below is the adapter matrix: each row is one config switch (§3.8).

| Concern | Local (now) | GCP (later) |
|---|---|---|
| Postgres | Homebrew PostgreSQL 17 on 5432 (host setup), or the `pgvector/pgvector` container on 5433 (Docker) | Cloud SQL Postgres 17 + pgvector |
| Object storage | Real GCS bucket `knowhub-data` with the `raw/` and `media/` prefixes (host setup, via ADC), or `fake-gcs-server` (Docker) | The same bucket layout |
| Messaging | Pub/Sub emulator (`gcloud beta emulators pubsub`) | Pub/Sub |
| Transcoding | `media-worker` runs **FFmpeg** → HLS (360p/720p) + thumbnails | Transcoder API |
| Upload trigger | Browser calls `POST /uploads/{id}/complete` → publishes `video-uploaded` (fake-gcs has no bucket notifications) | Same call; GCS notification as backup. Worker is idempotent |
| Video delivery | Served straight from fake-gcs URL | Cloud CDN |
| Analytics | `analytics_events` table in Postgres | Pub/Sub → BigQuery subscription |
| AI (LLM + embeddings) | Ollama, or any cloud provider by API key (`PROVIDER`). `PROVIDER=none` disables AI | Vertex AI on ADC, or the same cloud providers |
| Workers | Pull subscribers as compose services — **not built yet**; the API does the work inline | Cloud Run (push) |

Compose services: `postgres`, `gcs`, `pubsub`, `ollama`, `api`, `media-worker`, `notify-worker`, `embed-worker`, `web`, plus a one-off `init` job. It runs the provisioning scripts from §3.10: create DB → migrate → seed → buckets → Pub/Sub topics and subscriptions → AI models.

**Local "done" check:** from a fresh clone on any machine, set up with `make` (or
`./scripts/bootstrap.sh`) → open `http://localhost:3000` → browse as anonymous → register →
upload video + short with AI-improved description → it processes and plays → like, comment,
share to another user → manage it from your channel → subscriber gets a notification →
search finds it. Everything up to and including "manage it from your channel" works today;
the notification bell and search are the next gaps (§1.1).

### 3.8 Configuration (single source for all GCP and app settings)
All settings live in **one typed config module**, `backend/app/core/config.py` (pydantic-settings). It is loaded from environment variables / `.env` files, with nested groups. Nothing GCP-specific is hardcoded anywhere else. Files: `.env.example` (committed, documented) and `.env` (local, git-ignored). GCP environments get values from Secret Manager / Cloud Run env.

`APP_ENV=local|dev|prod` plus **backend switches** choose each implementation:

| Group | Keys (examples) | Local value | GCP value |
|---|---|---|---|
| app | `APP_ENV`, `API_BASE_URL`, `WEB_BASE_URL`, `CORS_ORIGINS` | `local`, `http://localhost:8000`, … | per env |
| db | `DATABASE_URL` | `postgresql+asyncpg://knowhub:knowhub@postgres:5432/knowhub` | Cloud SQL connector |
| auth | `JWT_SECRET`, `ACCESS_TOKEN_TTL_MIN`, `REFRESH_TOKEN_TTL_DAYS` | dev secret | Secret Manager |
| gcp | `GCP_PROJECT_ID`, `GCP_REGION`, `GOOGLE_APPLICATION_CREDENTIALS` | `knowhub-local`, `us-central1`, none | real project |
| storage | `STORAGE_BACKEND` (`gcs`), `GCS_ENDPOINT_URL`, `GCS_RAW_BUCKET`, `GCS_MEDIA_BUCKET`, `SIGNED_URL_TTL_MIN`, `MEDIA_PUBLIC_BASE_URL` | `http://gcs:4443`, `knowhub-raw`, `knowhub-media` | empty endpoint, CDN URL |
| pubsub | `PUBSUB_EMULATOR_HOST`, `PUBSUB_TOPIC_VIDEO_UPLOADED`, `…_TRANSCODE_EVENTS`, `…_VIDEO_PUBLISHED`, `…_VIDEO_METADATA_CHANGED`, `…_ANALYTICS_EVENTS`, subscription names | `pubsub:8085` | unset |
| transcoder | `TRANSCODER_BACKEND` (`ffmpeg`/`gcp`), `TRANSCODER_LOCATION`, `TRANSCODER_PRESET` | `ffmpeg` | `gcp` |
| analytics | `ANALYTICS_BACKEND` (`postgres`/`bigquery`), `BQ_DATASET`, `BQ_EVENTS_TABLE` | `postgres` | `bigquery` |
| ai | `PROVIDER` (`openai`/`anthropic`/`gemini`/`vertex`/`ollama`/`none`), `MODEL`, `LLM_API_BASE`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `VERTEX_LOCATION`, `AI_EMBEDDING_MODEL`, `AI_EMBEDDING_DIM`, `AI_ENHANCE_MAX_CHARS` | `ollama`, `llama3.2` (3B, ~2 GB), `nomic-embed-text`, `768` | any cloud provider by key, or `vertex` on ADC |
| limits | `MAX_VIDEO_BYTES`, `MAX_VIDEO_SECONDS`, `MAX_SHORT_SECONDS` | 5 GB, 7200, 60 | same |

Code uses small **adapter interfaces** picked by these switches: `StorageService`, `EventBus`, `Transcoder`, `AnalyticsSink`, `TextGenerator`, `Embedder`. Moving from local to GCP only changes config.

### 3.9 AI design
**Writing assist (now)**
- `POST /api/v1/ai/enhance` 🔒 with `{ field: "title"|"description"|"tags", text, context: {title, topic, category, type} }` → `{ suggestion, (for tags) items[] }`.
- Prompts live in versioned files, `backend/app/ai/prompts/*.md`. For descriptions, the prompt keeps technical facts unchanged (no invented details), structures the text as *Problem / Root cause / Fix / Takeaways*, and fixes grammar and clarity.
- Runs through `TextGenerator` (Ollama locally, Vertex Gemini on GCP). Guards: login required, input length limit, per-user rate limit, timeout with a clear error. Upload still works if AI is down.

**Embeddings for future semantic search (stored now)**
- On `video-published` or `video-metadata-changed`, `embed-worker` builds the text `title + description + topics + tags`, hashes it, and (if the hash changed) calls `Embedder`. It upserts into `video_embeddings`.
- Each row stores `model` and `dim`. Switching models means a re-embed job (`python -m app.scripts.reembed`), because vectors from different models aren't comparable.
- A backfill script embeds existing videos.
- Future query path: `GET /search?mode=semantic|hybrid` → embed the query → `ORDER BY embedding <=> :q` (HNSW index), merged with full-text rank (reciprocal rank fusion).


**Switching provider (built).** `PROVIDER` chooses where the writing assist runs. Each
provider carries its own key and its own default model, so switching is usually two lines
in `.env`:

| `PROVIDER` | Key | Default `MODEL` | Endpoint |
|---|---|---|---|
| `openai` | `OPENAI_API_KEY` | `gpt-4.1-mini` | `https://api.openai.com` |
| `anthropic` | `ANTHROPIC_API_KEY` | `claude-sonnet-5` | `https://api.anthropic.com` |
| `gemini` | `GEMINI_API_KEY` | `gemini-2.5-flash` | `https://generativelanguage.googleapis.com` |
| `vertex` | none — Application Default Credentials | `gemini-2.5-flash` | `{VERTEX_LOCATION or GCP_REGION}-aiplatform.googleapis.com` |
| `ollama` | none — runs locally | `llama3.2` | `LLM_API_BASE` |
| `none` | — | — | the assist is switched off |

- **`MODEL`** overrides the default. **`LLM_API_BASE`** overrides the endpoint — it is not
  needed to reach OpenAI, Anthropic, Gemini or Vertex, which have their own. Setting it to
  `http://localhost:11434` with `PROVIDER=openai` runs against anything OpenAI-compatible
  — Ollama, vLLM, LiteLLM, a company proxy. A base that already ends in `/v1` is not
  doubled, and `LLM_BASE_URL` / `OLLAMA_BASE_URL` are accepted as the same setting.
- Two mix-ups are refused at startup rather than failing later as a confusing 404: a base
  URL pointing at one provider's host while `PROVIDER` names another, and a local model
  name (`llama…`, `mistral…`) on a cloud provider. `PROVIDER` is case-insensitive.
- Every provider is called over its REST API with httpx, so **no provider SDK is a
  dependency**. Three request shapes cover all five: OpenAI chat completions, Anthropic
  messages, and Gemini `generateContent` (shared by AI Studio and Vertex, which differ only
  in host and auth).
- Keys never reach a URL: Gemini's travels in the `x-goog-api-key` header rather than the
  query string, so it cannot end up in an access log.
- Failures name their own fix: a missing or rejected key names the `.env` setting, an
  unknown model names `MODEL`, a disabled Vertex API gives the `gcloud services enable`
  command, and blocked or truncated answers are reported rather than returned as silence.
- `/api/v1/health` checks the live provider — a models listing for OpenAI, Anthropic and
  Gemini, `countTokens` for Vertex (free, but still proves credentials, the enabled API and
  the model), `/api/tags` for Ollama.
- The older `AI_PROVIDER`, `AI_TEXT_MODEL` and `OLLAMA_BASE_URL` names still work, so an
  existing `.env` keeps running.

### 3.10 Database & resource provisioning (everything by script, zero manual steps)
**Principle:** a new machine (or a new GCP project) goes from empty to fully working by running scripts. No clicking in consoles and no hand-typed SQL. Every script is:
- **idempotent**: safe to run again; it creates what's missing and skips what exists
- **config-driven**: names and hosts come from the same `.env` / config (§3.8)
- **target-aware**: `--target local` (emulators) or `--target gcp` (a real project)

**`database/` holds all database work.** All DDL, migrations, seeds, BigQuery definitions and database scripts live here. The backend only *uses* the schema; it never creates it.
```
database/
  README.md                      # how to run everything below
  postgres/
    init_db.sql                  # FIRST script: role, database, privileges, extensions
    migrations/                  # the ONLY way the schema changes; forward-only, versioned
      V001__extensions.sql       # pg_trgm + shared set_updated_at() trigger function
      V002__users_auth.sql       # users, refresh_tokens
      V003__topics.sql
      V004__videos.sql           # videos, video_topics, tags, video_tags, video_links, upload_events
      V005__video_edits.sql
      V006__engagement.sql       # reactions, comments, shares, playlists, watch_history
      V007__subscriptions_notifications.sql
        V008__ai_embeddings.sql    # CREATE EXTENSION vector, video_embeddings (+ HNSW), ai_requests
      V009__analytics_local.sql  # analytics_events (local stand-in for BigQuery)
    seeds/
      common/001_topics.sql      # GCP topics list (BigQuery, Pub/Sub, GKE, …), all envs
      local/010_demo_users.sql   # demo users/passwords, local only
      local/020_sample_videos.sql
    schema/schema.sql            # auto-generated snapshot (pg_dump --schema-only) for reading and review
  bigquery/
    ddl/
      001_dataset.sql            # CREATE SCHEMA IF NOT EXISTS knowhub_analytics
      002_events.sql             # CREATE TABLE IF NOT EXISTS events (partitioned by day, clustered by video_id)
      003_views.sql              # views: daily_video_stats, trending_7d
    queries/                     # saved queries used by the app (trending, studio stats)
  scripts/
    init_db.sh                   # run init_db.sql using the values from DATABASE_URL
    migrate.py                   # apply pending migrations, record in schema_migrations (version + checksum)
    seed.py                      # run seeds/common + seeds/<APP_ENV>
    reset_local.sh               # drop + recreate + migrate + seed (refuses unless APP_ENV=local)
    dump_schema.sh               # regenerate postgres/schema/schema.sql
    bq_apply.py                  # apply bigquery/ddl/*.sql in order (gcp target)
```

**Migration rules**
- Plain SQL files `V<NNN>__<name>.sql`. The runner (`migrate.py`, Python + psycopg) applies them in order, each in a transaction. It records version and checksum in `schema_migrations`.
- If an already-applied file is edited, the checksum no longer matches and the run fails. Schema changes are always a **new** file.
- `migrate.py status` shows applied and pending migrations. SQLAlchemy models in the backend mirror the tables but never create them.

**`infra/` holds all other resources as scripts.**
```
infra/
  README.md
  scripts/
    provision.py        # one entry point: python infra/scripts/provision.py --target local|gcp
    gcs.py              # buckets (knowhub-raw, knowhub-media), CORS for browser uploads, lifecycle (raw → Coldline 30d), public-read/CDN on media (gcp)
    pubsub.py           # topics, subscriptions, dead-letter topics, retry policy; GCS→Pub/Sub notification (gcp)
    bigquery.py         # dataset + tables via database/bigquery/ddl, Pub/Sub→BigQuery subscription (gcp)
    gcp_project.py      # (gcp only) enable APIs, service accounts + IAM roles, Artifact Registry, Secret Manager secrets, Cloud SQL instance
    ollama_models.sh    # pull configured AI models (local)
  docs/                 # what each resource is for, naming conventions, required IAM
```
Python scripts use the Google Cloud client libraries, which automatically talk to the emulators when `PUBSUB_EMULATOR_HOST` / `STORAGE_EMULATOR_HOST` are set. So the same script provisions local and GCP. BigQuery has no official emulator, so it's provisioned only on `--target gcp`; locally, analytics go to Postgres.

Setup order is always: `init_db.sql` → migrations → seeds.

**One command per machine**
```
./scripts/bootstrap.sh            # local: check docker → create .env from .env.example if missing
                                  #   → start postgres/gcs/pubsub/ollama → wait healthy
                                  #   → init_db.sql → migrate → seed → provision --target local
                                  #   → pull AI models → start api, workers, web
./scripts/bootstrap.sh --target gcp --env dev   # same steps against a GCP project
```
`docker compose up` also runs this automatically through a one-off `init` service, so even plain compose needs no extra steps. `make` targets wrap the common commands (`make bootstrap`, `make migrate`, `make seed`, `make reset-local`, `make provision`).

## 4. Tech Stack
| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js 16 + React 19 + TypeScript (Node 24 in containers), Tailwind CSS, TanStack Query, hls.js ⚙️ | Fast first load with SSR, rich ecosystem, easy video-site layout |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) + asyncpg | Chosen by the project. Async, typed, auto OpenAPI docs |
| Auth | pwdlib[argon2], PyJWT | Standard, secure |
| DB | Cloud SQL PostgreSQL 16 (+ `pg_trgm`, later `pgvector`) | Chosen by the project. Full-text search built in |
| Storage | Google Cloud Storage | Chosen by the project |
| Video | Transcoder API, FFprobe in worker | Managed ABR transcoding, no FFmpeg fleet |
| Messaging | Pub/Sub | Native GCP event bus |
| Analytics | BigQuery (Pub/Sub → BigQuery subscription) | No-code ingestion, SQL analytics |
| Hosting | Cloud Run (web, api, workers) | Serverless, scales to zero, simple |
| CDN | External HTTPS LB + Cloud CDN | Low-latency video delivery |
| DB migrations | Plain versioned SQL in `database/postgres/migrations` + Python runner (`migrate.py`) ⚙️ | DDL is readable SQL, tool-independent, checksum-protected |
| Provisioning | Python scripts (google-cloud client libs, `gcloud` where needed) in `infra/scripts` | Same script for emulators and GCP; no manual setup |
| CI/CD | GitHub Actions → Artifact Registry → Cloud Run | |
| AI | OpenAI, Anthropic, Gemini, Vertex AI or Ollama behind one `PROVIDER` switch, all called over plain HTTP with no SDK; `pgvector` for vectors | Writing assist now, semantic search later, all in the same DB |
| Config | pydantic-settings, `.env` / `.env.example`, backend switches | One place for all GCP and app settings |
| Local dev | docker-compose: Postgres+pgvector, fake-gcs-server, Pub/Sub emulator, Ollama, FFmpeg worker | Every feature runs on a laptop (§3.7) |
| Testing | pytest + httpx (API), Playwright (UI) | |

## 5. Data Model (PostgreSQL)
All tables use `id UUID PK`, `created_at`, `updated_at`.

| Table | Key columns |
|---|---|
| **users** | email (unique), password_hash, display_name, handle (unique, @handle), avatar_url, banner_url, bio, role (`user`/`admin`), team_id → teams, is_active, last_login_at |
| **refresh_tokens** | user_id → users, token_hash, expires_at, revoked_at, revoked_reason (`rotated`/`logout`/`reuse_detected`/`password_reset`/`admin`), user_agent, ip |
| **password_reset_tokens** | user_id → users, token_hash (SHA-256), expires_at, used_at, requested_ip, user_agent. Single use, 30 min (`PASSWORD_RESET_TTL_MIN`) |
| **topics** | slug (`bigquery`), name, description, icon. Admin-managed list of GCP services / areas |
| **teams** | slug (`payments`), name, description, division, sort_order, is_active. Which part of the organisation a video comes from |
| **videos** | owner_id → users, type (`video`/`short`), title, description, category, primary_topic_id → topics, team_id → teams, visibility (`internal`/`unlisted`/`restricted`/`private`), comments_enabled, status (`UPLOADING`/`PROCESSING`/`READY`/`FAILED`), raw_gcs_path, hls_path, thumbnail_path, duration_sec, width, height, size_bytes, view_count, like_count, comment_count, published_at, deleted_at, search_vector (tsvector, generated) |
| **video_viewers** | video_id, user_id, added_by, created_at. The allow-list behind visibility `restricted` |
| **video_topics** | video_id, topic_id (additional topics, many-to-many) |
| **tags / video_tags** | free-form tags |
| **video_links** | video_id, kind (`incident`/`jira`/`repo`/`pr`/`doc`), url, label |
| **upload_events** | video_id, user_id, event (`initiated`/`uploaded`/`processing`/`ready`/`failed`/`published`/`edited`/`visibility_changed`/`comments_changed`/`deleted`), metadata JSONB, created_at. **The audit trail of who uploaded what and when** |
| **video_reactions** | user_id, video_id, value (+1 like / -1 dislike), PK(user_id, video_id) |
| **comments** | video_id, user_id, parent_id (nullable, for replies), body, like_count, is_pinned, edited_at, deleted_at |
| **comment_reactions** | user_id, comment_id |
| **topic_subscriptions** | user_id, topic_id, notify (bool) |
| **channel_subscriptions** | subscriber_id, channel_user_id, notify (bool) |
| **notifications** | user_id, type (`new_video_topic`/`new_video_channel`/`comment_reply`/`video_ready`), video_id, actor_id, payload JSONB, read_at |
| **playlists / playlist_items** | owner_id, title, visibility; playlist_id, video_id, position (Watch Later = system playlist) |
| **watch_history** | user_id, video_id, last_position_sec, watched_at |
| **video_edits** | video_id, version (int), edit_list JSONB (`trims`, `cuts[]`, `crop`, `rotate`, `mute_ranges[]`, `thumbnail_time`), status (`draft`/`processing`/`applied`/`failed`), created_by, created_at. `videos.current_edit_version` points to the live one |
| **video_shares** | video_id, from_user_id, to_user_id, message, created_at (in-app sharing; also creates a notification) |
| **video_embeddings** | video_id (PK/FK), embedding `vector(768)`, model, dim, content_hash, updated_at. **Title + description (+ topics, tags) embeddings for semantic search** |
| **ai_requests** | user_id, field, model, input_chars, latency_ms, accepted (bool), created_at. Usage and quality tracking for the writing assist |
| **analytics_events** _(local only)_ | event_type, video_id, user_id/session_id, payload JSONB, created_at. Stands in for BigQuery locally |

Indexes: GIN on `videos.search_vector`, trigram on `videos.title`, `(status, visibility, published_at DESC)` for the feed, `(user_id, read_at)` on notifications, and HNSW (`vector_cosine_ops`) on `video_embeddings.embedding`.

All of the above is defined as SQL migrations in `database/postgres/migrations/` (§3.10). BigQuery tables (`knowhub_analytics.events` + views) are in `database/bigquery/ddl/`.

## 6. API Design (FastAPI, `/api/v1`)
🔓 = public, 🔒 = login required

- **Auth**: `POST /auth/register` 🔓 · `POST /auth/login` 🔓 · `POST /auth/refresh` 🔓 · `POST /auth/logout` 🔒 · `GET /auth/me` 🔒
- **Users/Channels**: `GET /channels/{handle}` 🔓 (profile + videos; the owner also gets hidden/processing ones and each video's viewer list) · `PATCH /users/me` 🔒
- **Uploads**: `POST /uploads` 🔒 (returns video_id + signed URL) · `POST /uploads/{id}/complete` 🔒 · `POST /videos/{id}/thumbnail-upload-url` 🔒
- **Video editing**: `GET /videos/{id}/edits` 🔒 owner · `PUT /videos/{id}/edits` 🔒 owner (save draft edit list) · `POST /videos/{id}/edits/apply` 🔒 owner (process it)
- **AI**: `POST /ai/enhance` 🔒 (improve title/description, suggest tags)
- **Sharing**: `POST /videos/{id}/share` 🔒 (to user ids) · `GET /shared-with-me` 🔒 · `GET /users/search?q=` 🔒 (pick recipients)
- **Videos**: `GET /videos/feed?type=&topic=&cursor=` 🔓 · `GET /videos/trending` 🔓 · `GET /videos/{id}` 🔓 · `GET /videos/{id}/related` 🔓 · `PATCH /videos/{id}` 🔒 owner (wording, topic, category, visibility, `comments_enabled`, `viewer_ids`, links, snippets) · `DELETE /videos/{id}` 🔒 owner (soft delete + removes the files)
- **Shorts**: `GET /shorts/feed?cursor=` 🔓
- **Search**: `GET /search?q=&type=&topic=&category=&date=&duration=&sort=` 🔓 · `GET /search/suggest?q=` 🔓 · _future:_ `&mode=semantic|hybrid`
- **Engagement**: `POST /videos/{id}/view` 🔓 · `PUT /videos/{id}/reaction` 🔒 · `GET /videos/{id}/comments?sort=&cursor=` 🔓 · `POST /videos/{id}/comments` 🔒 · `PATCH/DELETE /comments/{id}` 🔒 · `PUT /comments/{id}/reaction` 🔒
- **Subscriptions**: `GET /topics` 🔓 · `GET /teams` 🔓 · `PUT/DELETE /topics/{slug}/subscription` 🔒 · `PUT/DELETE /channels/{handle}/subscription` 🔒 · `GET /subscriptions/feed` 🔒
- **Notifications**: `GET /notifications` 🔒 · `GET /notifications/unread-count` 🔒 · `POST /notifications/{id}/read` 🔒 · `POST /notifications/read-all` 🔒
- **Library**: `GET/POST /playlists` 🔒 · `POST/DELETE /playlists/{id}/items` 🔒 · `GET /history` 🔒 · `DELETE /history` 🔒
- **Studio**: `GET /studio/videos` 🔒 · `GET /studio/videos/{id}/analytics` 🔒
- **Internal** (Pub/Sub push, OIDC-verified): `POST /internal/events/gcs-upload` · `POST /internal/events/transcode` · `POST /internal/events/video-published`

Pagination is cursor-based. Errors use RFC 7807 problem JSON.

## 7. Repository Layout (monorepo)
```
KnowHub/
  project.md                 # this doc
  frontend/                  # Next.js app (App Router, Tailwind v4)
    app/   built:   /, /watch/[id], /upload, /channel/[handle], /login, /register
           planned: /shorts/[id], /results, /studio, /feed/subscriptions
    components/ (AppShell, Sidebar, TopBar, VideoCard, VideoThumbnail, VideoPlayer,
                 UploadForm, Comments, AiAssist, ShareDialog, ChannelVideos,
                 VideoManageDialog…)
    lib/ (api.ts, session.ts, upload.ts, thumbnail.ts)
  backend/
    app/
      main.py
      core/ (config.py ← all settings, security, db, deps)
      adapters/      # storage (gcs/fake-gcs), eventbus (pubsub), transcoder (ffmpeg/gcp), analytics (pg/bq), ai (ollama/vertex)
      ai/prompts/    # versioned prompt files for writing assist
      models/        # SQLAlchemy
      schemas/       # Pydantic
      api/v1/        # built: health, auth, topics, videos, channels, engagement, ai
                     # planned: search, subscriptions, notifications, playlists, studio, internal
      services/      # business logic (auth, video, engagement, ai_assist, health)
      workers/       # planned: media_worker.py, notify_worker.py, embed_worker.py
      scripts/       # reembed.py (app-level jobs only)
    tests/
  database/                  # ALL database work: Postgres migrations/DDL, seeds, BigQuery DDL + queries, DB scripts (§3.10)
  infra/                     # provisioning scripts: GCS, Pub/Sub, BigQuery, GCP project setup, AI models (§3.10)
  scripts/bootstrap.sh       # one command: new machine → running app
  Makefile                   # install, db-init, db-reset, db-status, api, web, test, lint, docker targets
  docker-compose.yml         # postgres(pgvector), fake-gcs, pubsub-emulator, ollama, init, api, workers, web
  .env.example               # every config key, documented
  .github/workflows/
```

## 8. Implementation Roadmap
| Phase | Scope | Outcome |
|---|---|---|
| **0. Foundations** ✅ built | Monorepo scaffold, `config.py` + `.env.example`, adapter interfaces, docker-compose with all emulators (Postgres+pgvector, fake-gcs, Pub/Sub, Ollama), `database/` (migration runner, first migrations, seeds), `infra/scripts/provision.py` (buckets, topics, subscriptions), `scripts/bootstrap.sh` + Makefile, FastAPI + Next.js skeletons, CI lint/test | Fresh machine → `./scripts/bootstrap.sh` → everything running, zero manual steps |
| **1. Auth & users** | users/refresh_tokens tables, register/login/refresh/logout/me, login UI, protected routes | Users can sign up and log in |
| **2. Upload pipeline + AI assist** ✅ built (no transcoding yet) | Signed-URL upload, per-user GCS folders, upload dialog with metadata, **"Improve with AI" for title/description/tags**, upload_events audit, media-worker (FFmpeg locally), **embed-worker storing title+description embeddings** | Upload → processed HLS, AI-polished metadata, embeddings stored |
| **2b. Video editor** | In-browser editor: timeline to keep wanted time range(s) (trim/cut), crop box, thumbnail frame with local preview during upload; `video_edits` table; worker applies edit list (FFmpeg / Transcoder `editList`); re-edit after upload with versioned output | Users edit while uploading |
| **3. Watch & home** | Home feed, watch page with HLS player, channel page **(built: §2.5)**, view counts, the familiar layout (top bar, sidebar, chips) | Anonymous users can browse and watch |
| **4. Search** | Postgres FTS + trigram, filters, suggestions, results page | Users can find resolutions |
| **5. Engagement** | Likes/dislikes, comments and replies, in-app share to users + copy link/timestamp, Watch Later, playlists, history | The interactions people expect |
| **6. Subscriptions & notifications** | Topic and channel subscriptions, video-published Pub/Sub, notify-worker, bell UI, subscriptions feed | "New BigQuery resolution uploaded" alerts |
| **7. Shorts** | Shorts validation, vertical swipe feed, Shorts shelf on home | Shorts experience |
| **8. Studio & analytics** | Studio dashboard, analytics sink (Postgres locally / BigQuery on GCP), trending query, per-video stats | Creators see impact |
| **9. Semantic search** | Query embedding, vector + full-text hybrid ranking, "Similar resolutions" | Find videos by meaning, not just keywords |
| **10. GCP deploy & hardening** | `bootstrap.sh --target gcp` (APIs, IAM, Cloud SQL, buckets, Pub/Sub, BigQuery DDL), migrations against Cloud SQL, Cloud Run deploys, CDN, Secret Manager, Vertex AI, monitoring/alerts, rate limiting. Mostly a config switch thanks to §3.8 | Running in dev/stage/prod |
| **11. More AI** | Transcripts/captions, summaries/chapters, transcript embeddings | Smarter discovery |

**Phases 0–8 are fully local.** GCP deployment comes after the local app is feature-complete.

## 9. Non-functional Requirements
- **Security**: private raw bucket; signed URLs expire in 15 min; upload size and MIME validation; per-user folder isolation checked server-side; rate-limited auth endpoints; CORS locked to the web origin; audit via `upload_events`.
- **Performance**: API p95 < 300 ms for feed/search; playback start < 2 s through the CDN.
- **Reliability**: Pub/Sub handlers are idempotent (keyed by video_id and event), with dead-letter topics and retries.
- **Observability**: one log line per request with a request id (returned as `x-request-id` and carried on every line of that request), the signed-in user, status and duration. `LOG_LEVEL` and `LOG_FORMAT` in `.env`; `json` emits one object per line for Cloud Logging. Decisions that would otherwise be invisible are logged with their reason: why a 401 happened, which login check failed (the response stays identical), uploads starting and finishing, AI provider/model/latency, refresh-token reuse. Still to come: OpenTelemetry traces → Cloud Trace, error alerts.
- **Limits (configurable)**: video ≤ 5 GB / 2 h; short ≤ 60 s, vertical.

## 10. Open Questions / Decisions Log
| # | Question | Status |
|---|---|---|
| 1 | Is the app internal-only (behind IAP/VPN) with anonymous viewing inside the network, or reachable on the internet? | Open |
| 2 | Email/password only, or add Google Workspace SSO early? | Open (email/password for MVP) |
| 3 | Frontend framework: Next.js OK? | Proposed ⚙️ |
| 4 | Topic list: fixed GCP services seeded by admins, or can users create topics? | Open |
| 5 | Notification / sharing channels beyond in-app? | **Decided:** in-app only; sharing and notifications stay within KnowHub |
| 6 | Content moderation / reporting and retention policy? | Open |
| 7 | More upload metadata fields ("more coming soon") | Open |
| 8 | Transcoder API vs self-managed FFmpeg (cost vs control) | Proposed: FFmpeg locally, Transcoder API on GCP ⚙️ |
| 9 | Where does it run first? | **Decided:** local-first (docker compose); every function must work locally |
| 10 | Config management | **Decided:** single `config.py` + `.env`, all GCP settings in one place with backend switches |
| 11 | AI writing assist on upload | **Decided:** yes (title, description, tags; user accepts or rejects) |
| 12 | Semantic search | **Decided (future):** store title+description embeddings in pgvector from day one |
| 13 | Local AI provider: Ollama (offline, free) or Vertex AI from the laptop via ADC? | Proposed: Ollama ⚙️ |
| 14 | Embedding model/dimension (must stay consistent; switching requires re-embed) | Proposed: 768-dim ⚙️ |
| 15 | Video editing during upload | **Decided:** yes. v1 = keep wanted time range(s) (trim/cut) + crop the frame + thumbnail pick. Non-destructive, applied server-side, re-editable later. Rotate/mute/blur later |
| 16 | Editor UI: build our own timeline (HTML5 video + canvas), or use a library? Blur and captions editing in v1 or later? | Proposed: own lightweight timeline; blur/captions later ⚙️ |
| 17 | Where does DB work live / how are environments set up? | **Decided:** all DB work (DDL/migrations, seeds, BigQuery DDL + queries, scripts) in `database/`. GCS/Pub/Sub/BigQuery/GCP setup by idempotent scripts in `infra/`. One `bootstrap.sh` per machine, no manual steps |
| 18 | Migration tool: plain SQL + own runner, or an off-the-shelf tool (Flyway/dbmate)? Terraform later for GCP? | Proposed: plain SQL + `migrate.py`; scripts instead of Terraform for now ⚙️ |
| 19 | Upload transport for big files (10 MB failures through the Next.js proxy) | **Decided:** the browser uploads straight to GCS with a resumable session in 8 MB chunks; the API only hands out the session URL |
| 20 | Thumbnails without an FFmpeg dependency | **Decided:** capture the poster frame in the browser (`<video>` → `<canvas>` → JPEG) and upload it on publish; videos without one get a drawn cover |
| 21 | Per-video privacy: what does "limit it to a few people" mean? | **Decided:** a fourth visibility, `restricted`, with an allow-list in `video_viewers`. `unlisted` stays link-only, `private` is owner-only (§2.5) |
| 22 | Can an uploader turn comments off? | **Decided:** yes, per video (`videos.comments_enabled`). Comments already posted stay readable |
| 23 | Deleting a video | **Decided:** soft delete (`deleted_at`) so the audit trail survives; the file and thumbnail are removed from storage |
| 24 | Comment editing window | **Decided:** 60 s (`COMMENT_EDIT_WINDOW_SECONDS`), no countdown shown |
| 25 | Where do creator controls live: a separate Studio, or the channel page? | **Decided:** the channel page is the management surface (§2.5). Studio stays for analytics later |
