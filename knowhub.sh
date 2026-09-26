#!/usr/bin/env bash
# KnowHub: keep the BigQuery API and the web app running on this machine.
#
#   ./knowhub.sh start          check everything, then start whatever isn't running
#   ./knowhub.sh stop           stop both
#   ./knowhub.sh restart        stop, then start
#   ./knowhub.sh status         what is running, where, and when cron last ran
#   ./knowhub.sh logs           follow the logs (Ctrl+C to leave)
#   ./knowhub.sh cron-install   run `start` at every boot and every 10 minutes
#   ./knowhub.sh cron-remove    take those cron lines out again
#
# `start` is what cron runs. It only checks and starts: it never installs, builds or
# creates tables (that is the one-time setup in LOCAL_RUN.md), and it is safe to run as
# often as you like. Anything already running is left alone, so the every-10-minutes
# run is a watchdog that brings back whatever has stopped.
#
# Everything goes to logs/: api.log, web.log, and knowhub.log (what this script did,
# and why it refused to start if a check failed).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS="$ROOT/logs"
SELF="$ROOT/knowhub.sh"
ADC="$HOME/.config/gcloud/application_default_credentials.json"
LOG_MAX_BYTES=$((10 * 1024 * 1024))

# cron starts with an almost empty PATH; add where Homebrew puts python, node and npm
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

mkdir -p "$LOGS"

# ------------------------------------------------------------------ output
say() {
  local line
  line="$(date '+%Y-%m-%d %H:%M:%S') $*"
  echo "$line" >>"$LOGS/knowhub.log"
  [ -t 1 ] && echo "$*"
  return 0
}

fail() {
  say "NOT STARTED: $1"
  [ -n "${2:-}" ] && say "  fix: $2"
  exit 1
}

# ------------------------------------------------------------------ settings
load_env() {
  [ -f "$ROOT/.env" ] || fail "there is no .env file in $ROOT" \
    "follow step 3 of LOCAL_RUN.md (cp .env.example .env, then fill it in)"
  # shellcheck disable=SC1091
  source "$ROOT/scripts/localenv.sh" >/dev/null 2>&1 ||
    fail "could not read .env" "check the file for a line that is not KEY=value"
  RUN_ON_UPPER="$(echo "${RUN_ON:-PSQL}" | tr '[:lower:]' '[:upper:]')"
  API_PORT="${API_HOST_PORT:-8000}"
  WEB_PORT="${WEB_HOST_PORT:-3000}"
  WEB_URL="${WEB_BASE_URL:-http://localhost:$WEB_PORT}"
}

# ------------------------------------------------------------------ processes
pid_of() { cat "$LOGS/$1.pid" 2>/dev/null; }

# Running, and really ours: after a reboot the old pid in a .pid file can belong to some
# unrelated program, which must not count as "KnowHub is already running".
alive() {
  local pid command
  pid="$(pid_of "$1")"
  [ -n "$pid" ] || return 1
  command="$(ps -p "$pid" -o command= 2>/dev/null)" || return 1
  case "$1" in
    api) [[ "$command" == *"app_bq.main:app"* ]] ;;
    web) [[ "$command" == *next* ]] ;;
    *) return 1 ;;
  esac
}

api_healthy() { curl -fsS -m 5 "http://127.0.0.1:$API_PORT/healthz" >/dev/null 2>&1; }
web_healthy() { curl -sS -m 10 -o /dev/null "http://127.0.0.1:$WEB_PORT/" 2>/dev/null; }

port_owner() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $1 " (pid " $2 ")"}'
}

# Keep logs from filling the disk. copy-then-truncate, because the running app keeps
# writing to the same open file.
rotate() {
  local file="$LOGS/$1"
  [ -f "$file" ] || return 0
  if [ "$(stat -f%z "$file" 2>/dev/null || echo 0)" -gt "$LOG_MAX_BYTES" ]; then
    cp "$file" "$file.1" && : >"$file"
    say "rotated $1 (older lines are in $1.1)"
  fi
}

stop_one() {
  local name="$1" pid
  pid="$(pid_of "$name")"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    pkill -TERM -P "$pid" 2>/dev/null
    kill -TERM "$pid" 2>/dev/null
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$pid" 2>/dev/null; then
      pkill -KILL -P "$pid" 2>/dev/null
      kill -KILL "$pid" 2>/dev/null
    fi
    say "stopped $name (pid $pid)"
  fi
  rm -f "$LOGS/$name.pid"
}

# ------------------------------------------------------------------ checks
build_is_stale() {
  [ -f "$ROOT/frontend/.next/BUILD_ID" ] &&
    [ -n "$(find "$ROOT/frontend/app" "$ROOT/frontend/components" "$ROOT/frontend/lib" \
      -newer "$ROOT/frontend/.next/BUILD_ID" -type f 2>/dev/null | head -1)" ]
}

check_everything() {
  load_env

  [ "$RUN_ON_UPPER" = "BQ" ] || [ "$RUN_ON_UPPER" = "BIGQUERY" ] ||
    fail "RUN_ON=${RUN_ON:-PSQL} in .env, but this script runs the BigQuery version" \
      "set RUN_ON=BQ in .env"
  case "${JWT_SECRET:-}" in
    "" | change-me) fail "JWT_SECRET in .env is not set" \
      "run: openssl rand -hex 32   and paste the result after JWT_SECRET=" ;;
  esac
  [ -x "$ROOT/.venv/bin/uvicorn" ] ||
    fail "the Python packages are not installed" "run: make install"
  [ -d "$ROOT/frontend/node_modules" ] ||
    fail "the web app's packages are not installed" "run: make install"
  [ -f "$ROOT/frontend/.next/BUILD_ID" ] ||
    fail "the web app has not been built yet" "run: make build-web"
  # the build fixes where the web app sends /api calls; a later port change needs a rebuild
  grep -q "127.0.0.1:$API_PORT/" "$ROOT/frontend/.next/routes-manifest.json" 2>/dev/null ||
    fail "the web app was built for a different API port than API_HOST_PORT=$API_PORT" \
      "run: make build-web"
  [ -f "$ADC" ] || [ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] ||
    fail "this machine is not signed in to Google Cloud" \
      "run: gcloud auth application-default login"
  command -v node >/dev/null 2>&1 ||
    fail "node is not installed (or not where Homebrew puts it)" "run: brew install node"

}

# ------------------------------------------------------------------ start
start_api() {
  if alive api; then return 0; fi
  local owner
  owner="$(port_owner "$API_PORT")"
  [ -z "$owner" ] || fail "port $API_PORT (the API) is already used by $owner" \
    "stop that program, or set API_HOST_PORT and API_BASE_URL in .env to another port (e.g. 8001)"
  rotate api.log
  (
    cd "$ROOT/backend-bq" || exit 1
    PYTHONPATH=".:../backend" nohup "$ROOT/.venv/bin/uvicorn" app_bq.main:app \
      --host 127.0.0.1 --port "$API_PORT" >>"$LOGS/api.log" 2>&1 &
    echo $! >"$LOGS/api.pid"
  )
  for _ in $(seq 1 30); do
    api_healthy && { say "started API on http://127.0.0.1:$API_PORT (pid $(pid_of api))"; return 0; }
    alive api || break
    sleep 1
  done
  alive api && { say "API is starting (pid $(pid_of api)); still loading after 30s"; return 0; }
  fail "the API stopped right after starting" "see the last lines of logs/api.log"
}

start_web() {
  if alive web; then return 0; fi
  local owner
  owner="$(port_owner "$WEB_PORT")"
  [ -z "$owner" ] || fail "port $WEB_PORT (the web app) is already used by $owner" \
    "stop that program (maybe 'make web' in a terminal), or change WEB_HOST_PORT in .env"
  rotate web.log
  (
    cd "$ROOT/frontend" || exit 1
    API_INTERNAL_URL="http://127.0.0.1:$API_PORT" nohup ./node_modules/.bin/next start \
      --port "$WEB_PORT" >>"$LOGS/web.log" 2>&1 &
    echo $! >"$LOGS/web.pid"
  )
  for _ in $(seq 1 30); do
    web_healthy && { say "started web app on $WEB_URL (pid $(pid_of web))"; return 0; }
    alive web || break
    sleep 1
  done
  alive web && { say "web app is starting (pid $(pid_of web)); still loading after 30s"; return 0; }
  fail "the web app stopped right after starting" "see the last lines of logs/web.log"
}

cmd_start() {
  date '+%s' >"$LOGS/last-run"
  rotate knowhub.log
  check_everything
  if alive api && alive web; then
    return 0 # the usual case for the 10-minute watchdog: nothing to do, nothing logged
  fi
  if build_is_stale; then
    say "note: the web app code changed since it was built; run 'make build-web', then './knowhub.sh restart'"
  fi
  alive api || say "API is not running: starting it"
  start_api
  alive web || say "web app is not running: starting it"
  start_web
  say "KnowHub is up: $WEB_URL"
}

cmd_stop() {
  load_env
  stop_one web
  stop_one api
}

# ------------------------------------------------------------------ status
cmd_status() {
  load_env
  echo "KnowHub ($ROOT)"
  if alive api; then
    if api_healthy; then echo "  API       running  http://127.0.0.1:$API_PORT  (pid $(pid_of api))"
    else echo "  API       starting or stuck  (pid $(pid_of api)); see logs/api.log"; fi
  else
    echo "  API       stopped"
  fi
  if alive web; then
    if web_healthy; then echo "  Web app   running  $WEB_URL  (pid $(pid_of web))"
    else echo "  Web app   starting or stuck  (pid $(pid_of web)); see logs/web.log"; fi
  else
    echo "  Web app   stopped"
  fi

  if crontab -l 2>/dev/null | grep -F "$SELF" >/dev/null; then
    if [ -f "$LOGS/last-run" ]; then
      local ago=$(($(date +%s) - $(cat "$LOGS/last-run")))
      echo "  Cron      installed; last check $((ago / 60)) min ago"
      [ "$ago" -gt 1500 ] &&
        echo "            (should be every 10 min: see 'Full Disk Access' in LOCAL_RUN.md)"
    else
      echo "  Cron      installed, but has never run: see 'Full Disk Access' in LOCAL_RUN.md"
    fi
  else
    echo "  Cron      not installed (./knowhub.sh cron-install)"
  fi
  if build_is_stale; then
    echo "  Build     out of date: run 'make build-web', then './knowhub.sh restart'"
  fi
  echo "  Logs      $LOGS  (./knowhub.sh logs)"
}

# ------------------------------------------------------------------ cron
cmd_cron_install() {
  local current lines
  current="$(crontab -l 2>/dev/null | grep -vF "$SELF")"
  lines="@reboot \"$SELF\" start >>\"$LOGS/cron.log\" 2>&1
*/10 * * * * \"$SELF\" start >>\"$LOGS/cron.log\" 2>&1"
  { [ -n "$current" ] && printf '%s\n' "$current"; printf '%s\n' "$lines"; } | crontab - ||
    fail "could not update the crontab" "run: crontab -l   to see what is wrong"
  say "cron installed: start at boot, and check every 10 minutes"
  echo "Now give cron Full Disk Access (LOCAL_RUN.md, step 10), or macOS stops it from reading this folder."
}

cmd_cron_remove() {
  crontab -l 2>/dev/null | grep -vF "$SELF" | crontab -
  say "cron lines for KnowHub removed (the app keeps running until ./knowhub.sh stop)"
}

# ------------------------------------------------------------------ main
case "${1:-start}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_stop; cmd_start ;;
  status) cmd_status ;;
  logs) tail -n 40 -F "$LOGS/knowhub.log" "$LOGS/api.log" "$LOGS/web.log" ;;
  cron-install) cmd_cron_install ;;
  cron-remove) cmd_cron_remove ;;
  -h | --help | help) sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) echo "unknown command '$1'; try: ./knowhub.sh help" >&2; exit 2 ;;
esac
