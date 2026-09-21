#!/usr/bin/env bash
# Runs inside the `init` container on every `docker compose up`:
# database (init_db.sql → migrations → seeds), then cloud resources (buckets, topics, AI models).
# Every step is idempotent.
set -euo pipefail
cd /workspace

bash database/scripts/init_db.sh
python database/scripts/migrate.py up
python database/scripts/seed.py
python infra/scripts/provision.py --target local
echo "[init] complete"
