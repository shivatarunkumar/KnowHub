#!/usr/bin/env bash
# Source this to load .env for commands running on the host (not in docker):
#   source scripts/localenv.sh
# .env holds container hostnames (postgres, gcs, pubsub, host.docker.internal) because
# that is what the services use; here they are rewritten to localhost.
if [ -z "${BASH_VERSION:-}" ]; then
  echo "localenv.sh needs bash: run 'bash -c \"source scripts/localenv.sh && ...\"' or use the make targets" >&2
  return 1 2>/dev/null || exit 1
fi

set -a
# shellcheck disable=SC1091
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.env"
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
unset _var _value

# psql and other libpq tools don't understand SQLAlchemy driver prefixes
# (postgresql+asyncpg://); PSQL_URL is the same connection without them.
export PSQL_URL="${DATABASE_URL/+asyncpg/}"
export PSQL_URL="${PSQL_URL/+psycopg/}"
