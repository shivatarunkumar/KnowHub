# infra/

Scripts that create every non-database resource KnowHub needs. No console clicking.
Each script is **idempotent** (it creates what's missing and skips what exists) and **config-driven** (all names come from `.env`).

```
tools/Dockerfile      image the `init` job and Make targets run in (Python + client libraries)
scripts/
  provision.py        entry point: --target local|gcp, --only gcs,pubsub,ai
  resources.py        the list of buckets / topics / subscriptions / AI models (edit here to add one)
  gcs.py              buckets (+ CORS and lifecycle on GCP)
  pubsub.py           topics + subscriptions (+ dead-letter topics on GCP)
  ai_models.py        pull Ollama models (local AI)
```

## Targets
| | `--target local` | `--target gcp` |
|---|---|---|
| Storage | fake-gcs-server at `GCS_ENDPOINT_URL` | GCS in `GCP_PROJECT_ID` / `GCP_REGION` |
| Pub/Sub | emulator at `PUBSUB_EMULATOR_HOST` | Pub/Sub, with `<subscription>-dlq` dead-letter topics |
| Credentials | none (emulators) | Application Default Credentials (`gcloud auth application-default login` or a service account) |

Local runs refuse to start unless the emulator settings are present, so a local run can't create resources in a real project by accident.

`./scripts/bootstrap.sh` / `docker compose up` run `provision.py --target local` automatically via the `init` service. To re-run manually: `make provision`.

## Resources
| Resource | Default name | Purpose |
|---|---|---|
| Bucket | `knowhub-raw` | Original uploads, one folder per user (`users/{user_id}/videos/{video_id}/…`). Private. GCP: CORS for browser uploads, moves to Coldline after 30 days |
| Bucket | `knowhub-media` | Processed HLS renditions and thumbnails, served to the player |
| Topic | `video-uploaded` | Raw file finished uploading → media-worker |
| Topic | `transcode-events` | Transcoding finished/failed → media-worker |
| Topic | `video-published` | Video went live → notify-worker, embed-worker |
| Topic | `video-metadata-changed` | Title/description/tags edited → embed-worker |
| Topic | `analytics-events` | View/like events → BigQuery (GCP) |
| Subscriptions | `media-worker.*`, `notify-worker.*`, `embed-worker.*` | One per worker per topic (see `resources.py`) |
| Ollama models | `llama3.2`, `nomic-embed-text` | Writing assist and embeddings (local) |

The Pub/Sub emulator keeps everything in memory. After it restarts, the next `docker compose up` (the init job) re-creates topics and subscriptions.

## Still to come
- BigQuery dataset/tables (`database/bigquery/`): Phase 8
- GCP project setup (enable APIs, service accounts/IAM, Cloud SQL, Secret Manager, CDN access to `knowhub-media`): Phase 10
