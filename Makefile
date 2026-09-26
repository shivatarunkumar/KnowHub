# KnowHub developer commands.
#
#   make install    install every dependency (backend, database/infra tools, frontend)
#   make db-init    create the database, tables and seed data
#   make check-all  verify the tools, the database and the GCP connection
#   make api        run the API          make web    run the web app
#   make            list every command
#
# RUN_ON in .env picks the database: PSQL (default) or BQ. On BigQuery, run
# `make setup-bq` once instead of `make db-init`; `make api` then starts backend-bq/.
#
# Python packages go into a local .venv, so nothing is installed system-wide.

SHELL  := /bin/bash
PYTHON ?= python3
VENV   ?= .venv
PY     := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip
COMPOSE := docker compose
TOOLS  := $(COMPOSE) run --rm init
ARGS   ?=

.DEFAULT_GOAL := help
.PHONY: help check check-db check-gcp check-all install install-python install-web setup \
        db-init db-reset db-status db-shell api api-psql api-bq setup-bq setup-gcp setup-local \
        build-web web test test-bq lint \
        bootstrap up down logs ps provision dump-schema clean

help:  ## list every command
	@echo "KnowHub commands:"
	@grep -hE '^[a-z][a-z-]*:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[1m%-14s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup
# RUN_ON from .env (PSQL when there's no .env yet): decides which tools are needed
RUN_ON_ENV := $(shell grep -E '^RUN_ON=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr '[:lower:]' '[:upper:]')

check:  ## check the tools this project needs are installed (psql for PSQL, terraform for BQ)
	@missing=0; \
	tools="$(PYTHON) node npm"; \
	case "$(RUN_ON_ENV)" in BQ|BIGQUERY) tools="$$tools terraform gcloud" ;; *) tools="$$tools psql" ;; esac; \
	for tool in $$tools; do \
	  if command -v $$tool >/dev/null 2>&1; then \
	    printf "  ok      %-9s %s\n" "$$tool" "$$($$tool --version 2>&1 | head -1)"; \
	  else \
	    printf "  MISSING %-9s\n" "$$tool"; missing=1; \
	  fi; \
	done; \
	if [ $$missing -eq 1 ]; then \
	  echo; echo "Install what's missing:"; \
	  echo "  python3   → brew install python"; \
	  echo "  node/npm  → brew install node"; \
	  echo "  psql      → brew install postgresql@17"; \
	  echo "  terraform → brew install terraform"; \
	  echo "  gcloud    → brew install --cask gcloud-cli"; \
	  exit 1; \
	fi

install: check install-python install-web  ## install all dependencies (backend + tools + frontend)
	@case "$(RUN_ON_ENV)" in \
	  BQ|BIGQUERY) echo "✔ dependencies installed. Next: make setup-bq (or make setup-local, see LOCAL_RUN.md)" ;; \
	  *) echo "✔ dependencies installed. Next: make db-init" ;; \
	esac

install-python: | $(VENV)  ## backend + database/infra Python packages into .venv
	@echo "==> installing Python packages into $(VENV)"
	@$(PIP) install --quiet --upgrade pip
	@$(PIP) install --quiet -r backend/requirements-dev.txt -r backend-bq/requirements.txt \
	  -r infra/tools/requirements.txt
	@echo "    $$($(PY) -V), $$($(PIP) list --format=freeze | wc -l | tr -d ' ') packages"

install-web:  ## frontend npm packages
	@echo "==> installing npm packages in frontend/"
	@cd frontend && npm install --no-audit --no-fund --silent
	@echo "    node $$(node -v)"

$(VENV):
	@echo "==> creating virtualenv $(VENV)"
	@$(PYTHON) -m venv $(VENV)

setup: install db-init  ## install everything, then set up the database

setup-local: install setup-gcp setup-bq build-web  ## one-time BigQuery setup: install, GCP resources, tables, web build (LOCAL_RUN.md)
	@echo "✔ set up. Next: ./knowhub.sh start"

setup-gcp: | $(VENV)  ## create/update the GCS bucket (with upload CORS) and Pub/Sub topics in GCP_PROJECT_ID
	@source scripts/localenv.sh && $(PY) infra/scripts/provision.py --target gcp --only gcs,pubsub

build-web:  ## build the web app for ./knowhub.sh (production mode); re-run after pulling new code
	@source scripts/localenv.sh && cd frontend && \
	  API_INTERNAL_URL=http://127.0.0.1:$${API_HOST_PORT:-8000} npm run build

# ---------------------------------------------------------------- database
db-init: | $(VENV)  ## create database, role, tables and seed data (idempotent)
	@$(PY) database/scripts/setup_db.py $(ARGS)

db-reset: | $(VENV)  ## DROP the local database and rebuild it from scratch
	@$(PY) database/scripts/setup_db.py --reset --yes $(ARGS)

db-status: | $(VENV)  ## list applied / pending migrations
	@source scripts/localenv.sh && $(PY) database/scripts/migrate.py status

db-shell:  ## open psql on the KnowHub database
	@source scripts/localenv.sh && psql "$$PSQL_URL"

dump-schema:  ## regenerate database/postgres/schema/schema.sql
	@source scripts/localenv.sh && ./database/scripts/dump_schema.sh

check-db: | $(VENV)  ## verify the database: connection, schema, migrations, seeds
	@source scripts/localenv.sh && $(PY) database/scripts/check_db.py $(ARGS)

check-gcp: | $(VENV)  ## verify GCP: credentials, network, bucket, Pub/Sub topics
	@source scripts/localenv.sh && $(PY) infra/scripts/check_gcp.py $(ARGS)

check-all: check check-db check-gcp  ## run every check: tools, database, GCP

# ---------------------------------------------------------------- bigquery (RUN_ON=BQ)
setup-bq: | $(VENV)  ## BigQuery: create the dataset + every table (Terraform) and seed them (idempotent)
	@source scripts/localenv.sh && $(PY) infra/gcs/bq/setup_bq.py $(ARGS)

# ---------------------------------------------------------------- run
api: | $(VENV)  ## run the API RUN_ON names (PSQL or BQ) at http://localhost:8000
	@source scripts/localenv.sh && run_on=$$(echo "$${RUN_ON:-PSQL}" | tr '[:lower:]' '[:upper:]'); \
	case "$$run_on" in \
	  BQ|BIGQUERY) $(MAKE) --no-print-directory api-bq ;; \
	  PSQL|POSTGRES|POSTGRESQL) $(MAKE) --no-print-directory api-psql ;; \
	  *) echo "RUN_ON=$$RUN_ON in .env: use PSQL or BQ" >&2; exit 1 ;; \
	esac

api-psql: | $(VENV)  ## run the Postgres API (backend/) at http://localhost:8000
	@source scripts/localenv.sh && cd backend && \
	  ../$(VENV)/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port $${API_HOST_PORT:-8000}

api-bq: | $(VENV)  ## run the BigQuery API (backend-bq/) at http://localhost:8000
	@source scripts/localenv.sh && cd backend-bq && PYTHONPATH=.:../backend \
	  ../$(VENV)/bin/uvicorn app_bq.main:app --reload --reload-dir . --reload-dir ../backend/app \
	  --host 0.0.0.0 --port $${API_HOST_PORT:-8000}

web:  ## run the web app at http://localhost:3000
	@source scripts/localenv.sh && cd frontend && \
	  API_INTERNAL_URL=$${API_BASE_URL:-http://localhost:8000} npm run dev -- --port $${WEB_HOST_PORT:-3000}

# ---------------------------------------------------------------- quality
test: | $(VENV)  ## run backend + database tests and the frontend type check
	@source scripts/localenv.sh && cd backend && ../$(VENV)/bin/pytest -q
	@source scripts/localenv.sh && cd backend-bq && ../$(VENV)/bin/pytest -q
	@source scripts/localenv.sh && TEST_POSTGRES_ADMIN_URL="$$POSTGRES_ADMIN_URL" $(VENV)/bin/pytest -q database/tests
	@cd frontend && npm run typecheck

test-bq: | $(VENV)  ## run the BigQuery API tests against real BigQuery (throwaway dataset)
	@source scripts/localenv.sh && cd backend-bq && KNOWHUB_TEST_BQ=1 ../$(VENV)/bin/pytest -q $(ARGS)

lint: | $(VENV)  ## ruff lint + format check
	@$(VENV)/bin/ruff check . && $(VENV)/bin/ruff format --check .

# ---------------------------------------------------------------- docker (full stack)
bootstrap:  ## docker: one command to run everything (API, web, emulators)
	./scripts/bootstrap.sh

up:  ## docker: start all services
	$(COMPOSE) up -d --build

down:  ## docker: stop all services
	$(COMPOSE) down

logs:  ## docker: follow logs
	$(COMPOSE) logs -f --tail 100

ps:  ## docker: service status
	$(COMPOSE) ps -a

provision:  ## docker: create buckets, Pub/Sub topics/subscriptions, AI models
	$(TOOLS) python infra/scripts/provision.py --target local

clean:  ## remove .venv, node_modules and build output
	rm -rf $(VENV) frontend/node_modules frontend/.next
