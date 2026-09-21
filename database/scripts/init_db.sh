#!/usr/bin/env bash
# Step 1 of database setup: run database/postgres/init_db.sql as the admin user.
# Connection comes from POSTGRES_ADMIN_URL; the role, password and database name are
# taken from DATABASE_URL, so .env stays the single source of truth.
set -euo pipefail
cd "$(dirname "$0")/../.."

: "${POSTGRES_ADMIN_URL:?set POSTGRES_ADMIN_URL (see .env.example)}"
: "${DATABASE_URL:?set DATABASE_URL (see .env.example)}"

# postgresql+asyncpg://user:password@host:5432/dbname  →  user / password / dbname
rest="${DATABASE_URL#*://}"
creds="${rest%%@*}"
db_user="${creds%%:*}"
db_password="${creds#*:}"
db_name="${rest##*/}"
db_name="${db_name%%\?*}"

psql "$POSTGRES_ADMIN_URL" \
  --no-psqlrc --quiet -v ON_ERROR_STOP=1 \
  -v db_name="$db_name" -v db_user="$db_user" -v db_password="$db_password" \
  -f database/postgres/init_db.sql
