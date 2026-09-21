#!/usr/bin/env bash
# One command from a fresh clone to a running KnowHub. Safe to re-run at any time.
#
#   ./scripts/bootstrap.sh                 # local: docker compose + emulators
#   ./scripts/bootstrap.sh --only-db       # just Postgres: start it, create db, migrate, seed
#   ./scripts/bootstrap.sh --target gcp    # real GCP project (Phase 10)
#
# Needs only Docker (with the compose plugin) and bash on the host.
set -euo pipefail
cd "$(dirname "$0")/.."

TARGET=local
ONLY_DB=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="${2:-}"; shift 2 ;;
    --target=*) TARGET="${1#*=}"; shift ;;
    --only-db) ONLY_DB=true; shift ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

bold=$'\033[1m'; green=$'\033[32m'; yellow=$'\033[33m'; red=$'\033[31m'; reset=$'\033[0m'
step() { echo "${bold}==> $*${reset}"; }
warn() { echo "${yellow}WARNING:${reset} $*"; }
die()  { echo "${red}ERROR:${reset} $*" >&2; exit 1; }

if [[ "$TARGET" == "gcp" ]]; then
  die "GCP bootstrap arrives in Phase 10 (project.md §3.10). Local is the current target."
fi
[[ "$TARGET" == "local" ]] || die "--target must be local or gcp"

# ------------------------------------------------------------------ prerequisites
step "Checking Docker"
command -v docker >/dev/null || die "Docker is not installed: https://docs.docker.com/get-docker/"
docker compose version >/dev/null 2>&1 || die "the 'docker compose' plugin is missing (Docker Desktop includes it)"
if ! docker info >/dev/null 2>&1; then
  if [[ "$(uname)" == "Darwin" ]] && open -a Docker 2>/dev/null; then
    echo "    starting Docker Desktop…"
    for _ in $(seq 1 90); do docker info >/dev/null 2>&1 && break; sleep 2; done
  fi
  docker info >/dev/null 2>&1 || die "the Docker daemon is not running; start Docker and re-run"
fi

free_kb=$(df -Pk . | awk 'NR==2 {print $4}')
if (( free_kb < 8 * 1024 * 1024 )); then
  warn "only $((free_kb / 1024 / 1024)) GB of disk free; images + AI models need ~8 GB"
fi

# ------------------------------------------------------------------ .env
set_env() {  # set_env KEY VALUE: replace or append in .env
  local key=$1 value=$2
  if grep -q "^${key}=" .env; then
    awk -v k="$key" -v v="$value" 'index($0, k"=") == 1 { print k"="v; next } { print }' .env > .env.tmp
    mv .env.tmp .env
  else
    echo "${key}=${value}" >> .env
  fi
}

if [[ ! -f .env ]]; then
  step "Creating .env from .env.example"
  cp .env.example .env
  secret=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
  set_env JWT_SECRET "$secret"
  if curl -sf -m 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "    Ollama is already running on this machine: using it (no extra download)"
    set_env LLM_API_BASE "http://localhost:11434"
    set_env COMPOSE_PROFILES ""
  else
    echo "    no Ollama on this machine: it will run in docker (profile 'ollama')"
    set_env LLM_API_BASE "http://localhost:11434"
    set_env LLM_API_BASE_DOCKER "http://ollama:11434"
    set_env COMPOSE_PROFILES "ollama"
  fi
else
  step "Using existing .env"
fi
set -a; . ./.env; set +a

# ------------------------------------------------------------------ ports
if [[ -z "$(docker compose ps -q 2>/dev/null)" ]]; then
  port_in_use() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
  busy=()
  port_vars=(POSTGRES_HOST_PORT API_HOST_PORT WEB_HOST_PORT GCS_HOST_PORT PUBSUB_HOST_PORT)
  [[ "$ONLY_DB" == true ]] && port_vars=(POSTGRES_HOST_PORT)
  for var in "${port_vars[@]}"; do
    port="${!var}"
    port_in_use "$port" && busy+=("$var=$port")
  done
  if (( ${#busy[@]} )); then
    die "port(s) already in use: ${busy[*]}. Pick free ports for these keys in .env and re-run."
  fi
fi

# ------------------------------------------------------------------ database only
if [[ "$ONLY_DB" == true ]]; then
  step "Starting Postgres"
  docker compose up -d postgres
  step "Creating database, applying migrations, loading seeds"
  docker compose run --rm --no-deps init sh -c \
    "bash database/scripts/init_db.sh && python database/scripts/migrate.py up && python database/scripts/seed.py"
  db_url="${DATABASE_URL#*://}"            # knowhub:knowhub@postgres:5432/knowhub
  db_user="${db_url%%:*}"
  db_name="${db_url##*/}"
  cat <<EOF

${green}${bold}Postgres is ready.${reset}
  Database   ${db_name} (user ${db_user}) on localhost:${POSTGRES_HOST_PORT}
  psql       docker compose exec postgres psql -U ${db_user} -d ${db_name}
  From host  psql "postgresql://${db_url%%@*}@localhost:${POSTGRES_HOST_PORT}/${db_name}"
EOF
  exit 0
fi

# ------------------------------------------------------------------ start
step "Building images and starting services (first run downloads images; takes a few minutes)"
if ! docker compose up -d --build; then
  echo
  docker compose logs --no-color --tail 60 init || true
  die "startup failed; see the output above (init job logs)"
fi

step "Waiting for the API"
api="http://localhost:${API_HOST_PORT}"
for _ in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$api/api/v1/health" || true)
  [[ "$code" == "200" || "$code" == "503" ]] && break
  sleep 2
done
health=$(curl -s "$api/api/v1/health" || true)
status=$(echo "$health" | sed -n 's/.*"status":"\([a-z]*\)".*/\1/p' | head -1)
case "$status" in
  ok)       echo "    ${green}all services connected${reset}" ;;
  degraded) warn "API up, optional service unavailable: $health" ;;
  *)        docker compose logs --no-color --tail 40 api || true; die "API not healthy: ${health:-no response}" ;;
esac

step "Waiting for the web app (first run installs npm packages)"
web="http://localhost:${WEB_HOST_PORT}"
for _ in $(seq 1 150); do
  curl -sf -o /dev/null "$web" && break
  sleep 2
done
curl -sf -o /dev/null "$web" || { docker compose logs --no-color --tail 40 web || true; die "web app did not start"; }

cat <<EOF

${green}${bold}KnowHub is running.${reset}
  Web        $web
  API docs   $api/docs
  Health     $api/api/v1/health
  Postgres   localhost:${POSTGRES_HOST_PORT} (db/user/password from DATABASE_URL)

  Stop: make down     Logs: make logs     Re-run anytime: ./scripts/bootstrap.sh
EOF
