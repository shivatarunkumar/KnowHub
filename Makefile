# KnowHub developer commands.
#
#   make install    install every dependency (backend, database/infra tools, frontend)
#   make db-init    create the database, tables and seed data
#   make api        run the API          make web    run the web app
#   make            list every command
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
.PHONY: help check install install-python install-web setup db-init db-reset db-status db-shell \
        api web test lint bootstrap up down logs ps provision dump-schema clean

help:  ## list every command
	@echo "KnowHub commands:"
	@grep -hE '^[a-z][a-z-]*:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[1m%-14s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- setup
check:  ## check the tools this project needs are installed
	@missing=0; \
	for tool in $(PYTHON) node npm psql; do \
	  if command -v $$tool >/dev/null 2>&1; then \
	    printf "  ok      %-8s %s\n" "$$tool" "$$($$tool --version 2>&1 | head -1)"; \
	  else \
	    printf "  MISSING %-8s\n" "$$tool"; missing=1; \
	  fi; \
	done; \
	if [ $$missing -eq 1 ]; then \
	  echo; echo "Install what's missing:"; \
	  echo "  python3 → brew install python@3.12"; \
	  echo "  node/npm → brew install node"; \
	  echo "  psql     → brew install libpq (or postgresql@16)"; \
	  exit 1; \
	fi

install: check install-python install-web  ## install all dependencies (backend + tools + frontend)
	@echo "✔ dependencies installed. Next: make db-init"

install-python: | $(VENV)  ## backend + database/infra Python packages into .venv
	@echo "==> installing Python packages into $(VENV)"
	@$(PIP) install --quiet --upgrade pip
	@$(PIP) install --quiet -r backend/requirements-dev.txt -r infra/tools/requirements.txt
	@echo "    $$($(PY) -V), $$($(PIP) list --format=freeze | wc -l | tr -d ' ') packages"

install-web:  ## frontend npm packages
	@echo "==> installing npm packages in frontend/"
	@cd frontend && npm install --no-audit --no-fund --silent
	@echo "    node $$(node -v)"

$(VENV):
	@echo "==> creating virtualenv $(VENV)"
	@$(PYTHON) -m venv $(VENV)

setup: install db-init  ## install everything, then set up the database

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

# ---------------------------------------------------------------- run
api: | $(VENV)  ## run the API at http://localhost:8000 (reloads on change)
	@source scripts/localenv.sh && cd backend && \
	  ../$(VENV)/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port $${API_HOST_PORT:-8000}

web:  ## run the web app at http://localhost:3000
	@source scripts/localenv.sh && cd frontend && \
	  API_INTERNAL_URL=$${API_BASE_URL:-http://localhost:8000} npm run dev -- --port $${WEB_HOST_PORT:-3000}

# ---------------------------------------------------------------- quality
test: | $(VENV)  ## run backend + database tests and the frontend type check
	@source scripts/localenv.sh && cd backend && ../$(VENV)/bin/pytest -q
	@source scripts/localenv.sh && TEST_POSTGRES_ADMIN_URL="$$POSTGRES_ADMIN_URL" $(VENV)/bin/pytest -q database/tests
	@cd frontend && npm run typecheck

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
