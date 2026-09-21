#!/usr/bin/env bash
# Source this to load .env for commands running on the host (not in docker):
#   source scripts/localenv.sh
# .env holds container hostnames (postgres, gcs, pubsub, host.docker.internal) because
# that is what the services use; here they are rewritten to localhost.
if [ -z "${BASH_VERSION:-}" ]; then
  echo "localenv.sh needs bash: run 'bash -c \"source scripts/localenv.sh && ...\"' or use the make targets" >&2
  return 1 2>/dev/null || exit 1
fi

_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ ! -f "$_root/.env" ]; then
  cat >&2 <<'EOF'
No .env file yet. On a new machine:

  cp .env.example .env

then open .env and set, for the host setup (Postgres + real GCP on your machine):
  DATABASE_URL / POSTGRES_ADMIN_URL  your local Postgres user, password and port
  GCP_PROJECT_ID                     the GCP project that owns the bucket and topics
  GCS_ENDPOINT_URL=                  leave empty for real GCS (set only for the emulator)
  PUBSUB_EMULATOR_HOST=              leave empty for real Pub/Sub
  OLLAMA_BASE_URL                    where Ollama runs, or AI_PROVIDER=none

See the "Set up a second machine" section of the README.
EOF
  return 1 2>/dev/null || exit 1
fi

set -a
# shellcheck disable=SC1091
. "$_root/.env"
set +a

for _var in DATABASE_URL POSTGRES_ADMIN_URL OLLAMA_BASE_URL GCS_ENDPOINT_URL PUBSUB_EMULATOR_HOST; do
  _value="${!_var:-}"
  [[ -z "$_value" ]] && continue
  _value="${_value//host.docker.internal/localhost}"
  _value="${_value//"@postgres:"/"@localhost:"}"
  _value="${_value//"//gcs:"/"//localhost:"}"
  _value="${_value//"pubsub:"/"localhost:"}"
  export "$_var=$_value"
done
unset _var _value _root

# psql and other libpq tools don't understand SQLAlchemy driver prefixes
# (postgresql+asyncpg://); PSQL_URL is the same connection without them.
export PSQL_URL="${DATABASE_URL/+asyncpg/}"
export PSQL_URL="${PSQL_URL/+psycopg/}"
