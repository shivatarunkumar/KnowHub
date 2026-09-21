# GCP resources

Everything KnowHub uses in Google Cloud, what each thing is for, and which config key points at it.
Created 2026-09-20 in the console; from now on `infra/scripts/provision.py --target gcp` keeps this
in sync (it creates anything missing and never touches what exists).

**Project `bigquerytarun`** · region **europe-west2** (London) · billing enabled
Auth: application-default credentials (`gcloud auth application-default login`), no service-account key.

## Cloud Storage

| Bucket | Location | Holds | Config key |
|---|---|---|---|
| `knowhub-data` | europe-west2 | all video files, split by prefix | `GCS_BUCKET` |

One bucket, two prefixes:

| Prefix | Contents | Config key |
|---|---|---|
| `raw/users/{user_id}/videos/{video_id}/source.*` | the original uploaded file, one folder per user. Private; written by the browser through a signed URL | `GCS_RAW_PREFIX` |
| `media/videos/{video_id}/v{n}/hls/…`, `media/videos/{video_id}/thumbs/…` | processed HLS renditions and thumbnails, read by the player | `GCS_MEDIA_PREFIX` |

Settings the provisioning script applies: CORS for browser uploads (`GCS_CORS_ORIGINS`), and a
lifecycle rule moving `raw/` objects to Coldline after `GCS_RAW_COLDLINE_AFTER_DAYS` (30) days.

## Pub/Sub

| Topic | Published by | Consumed by | Config key |
|---|---|---|---|
| `video-uploaded` | API / GCS notification, when the upload finishes | media-worker: probe + transcode | `PUBSUB_TOPIC_VIDEO_UPLOADED` |
| `transcode-events` | Transcoder API, when a job ends | media-worker: mark READY or FAILED | `PUBSUB_TOPIC_TRANSCODE_EVENTS` |
| `video-published` | API, when a video goes live | notify-worker (notifications) **and** embed-worker (embeddings) | `PUBSUB_TOPIC_VIDEO_PUBLISHED` |
| `video-metadata-changed` | API, when title/description/tags change | embed-worker: re-embed | `PUBSUB_TOPIC_VIDEO_METADATA_CHANGED` |
| `analytics-events` | API, on views/likes/shares/searches | BigQuery subscription → `events_raw` | `PUBSUB_TOPIC_ANALYTICS_EVENTS` |
| `testtopic` | — | — | not used by KnowHub; safe to delete |

| Subscription | Topic | Used by | Config key |
|---|---|---|---|
| `video-uploaded-sub` | video-uploaded | media-worker | `PUBSUB_SUB_MEDIA_UPLOADED` |
| `transcode-events-sub` | transcode-events | media-worker | `PUBSUB_SUB_MEDIA_TRANSCODE` |
| `video-published-sub` | video-published | notify-worker | `PUBSUB_SUB_NOTIFY_PUBLISHED` |
| `video-published-embed-sub` | video-published | embed-worker | `PUBSUB_SUB_EMBED_PUBLISHED` |
| `video-metadata-changed-sub` | video-metadata-changed | embed-worker | `PUBSUB_SUB_EMBED_METADATA` |
| `analytics-events-sub` | analytics-events | currently a pull subscription; becomes a BigQuery subscription | — |

### Still to do
- **`video-published-embed-sub` does not exist yet.** Two workers must not share one subscription:
  Pub/Sub delivers each message to one subscriber per subscription, so notify-worker and
  embed-worker would steal each other's messages and half the videos would get no notification
  or no embedding. Each worker needs its own subscription on the same topic.
- **Ack deadlines are 10s**, the console default. Transcoding work needs longer, or messages get
  redelivered mid-job: 600s for `video-uploaded-sub`, 120s for `transcode-events-sub`,
  `video-published-embed-sub` and `video-metadata-changed-sub`.
- **`analytics-events-sub` should become a BigQuery subscription** writing into `events_raw`
  (with "write metadata" on), instead of a pull subscription.
- **Dead-letter topics** (`<subscription>-dlq`) so a repeatedly failing message stops retrying forever.

`provision.py --target gcp` does all four.

## BigQuery

Dataset **`bigquerytarun.knowhub_dataset`** (europe-west2) · `BQ_DATASET`, `BQ_PROJECT_ID`, `BQ_LOCATION`

| Object | Type | Purpose | Defined in |
|---|---|---|---|
| `events_raw` | table, day-partitioned on `publish_time`, 400-day expiry | landing table the Pub/Sub subscription writes into; keeps the raw JSON so new fields never break ingestion | `database/bigquery/ddl/001_events_raw.sql` |
| `events` | view | typed columns parsed out of the raw JSON: event_type, video_id, user_id, watch_seconds … | `002_events_view.sql` |
| `daily_video_stats` | view | per video per day: views, unique viewers, watch time, completions, likes, shares | `003_stats_views.sql` |
| `trending_7d` | view | last 7 days, engagement-weighted with recent days worth more; powers the Trending row | `003_stats_views.sql` |

Saved queries used by the API live in `database/bigquery/queries/`.

## APIs enabled
`storage.googleapis.com`, `storage-api.googleapis.com`, `pubsub.googleapis.com`,
`bigquery.googleapis.com`, `bigquerystorage.googleapis.com`.

Needed later: `transcoder.googleapis.com` (video processing), `aiplatform.googleapis.com`
(Vertex AI, if we move off Ollama), `run.googleapis.com` + `artifactregistry.googleapis.com`
+ `secretmanager.googleapis.com` (deployment, Phase 10).

## Not created yet
- **Cloud SQL**: the database still runs on the local Postgres 17 (`DATABASE_URL`). Phase 10.
- **Service account + IAM roles** for the deployed app. Phase 10; local runs use your own credentials.
- **Load balancer + Cloud CDN** in front of `media/`. Phase 10.
- **Transcoder API jobs**: local uses FFmpeg (`TRANSCODER_BACKEND=ffmpeg`).

## Using these from the app
```bash
set -a; . ./.env.gcp; set +a     # real GCP resources
make api                        # or: make web
```
`.env` (default) keeps local development on emulators and needs no cloud access.
