# SACCO Platform — common ops
#
# Pick up where the audit / Wave 4 work left off. Each target below
# is a one-liner you can otherwise tediously remember.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

# Default API host/port — matches what we used during manual testing
# (port 8000 was squatted on by another service when bringing the env up,
# so /readyz documentation favours :8001).
API_HOST ?= 127.0.0.1
API_PORT ?= 8001

# Override DATABASE_URL when shell exports a non-local value (a common
# gotcha during manual testing).
PY := env -u DATABASE_URL python
PYTEST := env -u DATABASE_URL pytest

.DEFAULT_GOAL := help

.PHONY: help up down api worker beat migrate seed-defaults seed-demo \
        materialize-reports test test-fast lint mypy ci provision-tenant \
        platform-token tail-api tail-worker

help: ## Show this list
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ── Docker compose lifecycle ──────────────────────────────────────────────────

up: ## Start postgres, redis, rabbitmq, elasticsearch (skips api)
	docker compose up -d postgres redis rabbitmq elasticsearch postgres-test
	@until docker compose exec -T postgres pg_isready -U sacco -d sacco >/dev/null 2>&1; do sleep 1; done
	@until docker compose exec -T redis redis-cli ping >/dev/null 2>&1; do sleep 1; done
	@echo "infra up: postgres=5432, postgres-test=5433, redis=6379, rabbitmq=5672, es=9200"

down: ## Stop all containers (keeps volumes)
	docker compose down

# ── App processes ─────────────────────────────────────────────────────────────

api: ## Run uvicorn (API_PORT=$(API_PORT))
	$(PY) -m uvicorn app.main:app --host $(API_HOST) --port $(API_PORT) --reload

worker: ## Run a Celery worker (registers all beat/consumer tasks)
	$(PY) -m celery -A app.workers.celery_app worker --loglevel=info --concurrency=2

beat: ## Run Celery beat (the scheduler)
	$(PY) -m celery -A app.workers.celery_app beat --loglevel=info

# ── Migrations & seeds ────────────────────────────────────────────────────────

migrate: ## Apply platform migrations (alembic/platform/) to the dev DB
	alembic upgrade head

seed-defaults: ## Seed default COA + fee_types into TENANT=<schema_name>
	@test -n "$(TENANT)" || (echo "Usage: make seed-defaults TENANT=tenant_sacco_one"; exit 2)
	$(PY) -c "import asyncio; from sqlalchemy.ext.asyncio import create_async_engine; from app.platform_.seeds.runner import seed_defaults; from app.core.config import get_settings; \
asyncio.run((lambda eng: seed_defaults(eng, '$(TENANT)'))(create_async_engine(get_settings().database_url)))"

seed-demo: ## Seed demo data (member + savings + loan + fee) into TENANT=<schema_name>
	@test -n "$(TENANT)" || (echo "Usage: make seed-demo TENANT=tenant_sacco_one"; exit 2)
	$(PY) -m app.platform_.seeds.smoke $(TENANT)

materialize-reports: ## Materialize all 5 reports into TENANT=<schema_name> for PERIOD_END (default 2026-01-31)
	@test -n "$(TENANT)" || (echo "Usage: make materialize-reports TENANT=tenant_sacco_one [PERIOD_END=2026-01-31]"; exit 2)
	$(PY) -c "import asyncio; from datetime import date; from sqlalchemy import text; from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker; \
from app.modules.reporting.services.trial_balance import TrialBalanceService; from app.modules.reporting.services.loan_portfolio import LoanPortfolioService; \
from app.modules.reporting.services.income_statement import IncomeStatementService; from app.modules.reporting.services.savings_statement import SavingsStatementService; \
from app.modules.reporting.services.fee_collection import FeeCollectionService; from app.core.config import get_settings; \
SCHEMA = '$(TENANT)'; PE = date.fromisoformat('$(or $(PERIOD_END),2026-01-31)'); PS = date(PE.year, PE.month, 1); \
async def _run(): \
    eng = create_async_engine(get_settings().database_url); factory = async_sessionmaker(eng, expire_on_commit=False); \
    for n, fn in [('trial_balance', lambda s: TrialBalanceService(s).materialize(as_of_date=PE)), ('loan_portfolio', lambda s: LoanPortfolioService(s).materialize(as_of_date=PE)), ('income_statement', lambda s: IncomeStatementService(s).materialize(period_start=PS, period_end=PE)), ('savings_statement', lambda s: SavingsStatementService(s).materialize(period_start=PS, period_end=PE)), ('fee_collection', lambda s: FeeCollectionService(s).materialize(period_start=PS, period_end=PE))]: \
        async with factory() as s: \
            await s.execute(text(f'SET LOCAL search_path TO {SCHEMA}, platform')); r = await fn(s); await s.commit(); print(f'{n}: status={r.status}') \n\
asyncio.run(_run())"

# ── Tests / lint ──────────────────────────────────────────────────────────────

test: ## Run the full test suite
	$(PYTEST) tests/ -q

test-fast: ## Run a single test or path, e.g. make test-fast T=tests/modules/reporting/test_trial_balance.py
	$(PYTEST) -q $(T)

lint: ## ruff check app/ tests/
	$(PY) -m ruff check app/ tests/

mypy: ## mypy app/
	$(PY) -m mypy app/

ci: lint mypy test ## Run everything CI runs (ruff + mypy + pytest)

# ── Helpers ───────────────────────────────────────────────────────────────────

platform-token: ## Print a platform admin Bearer token (uses .env credentials)
	@curl -s -X POST http://$(API_HOST):$(API_PORT)/platform/auth/token \
		-H 'Content-Type: application/json' \
		-d '{"email":"admin@platform.example.com","password":"AdminTest!2026"}' \
		| python -c "import json,sys; print(json.load(sys.stdin)['access_token'])"

provision-tenant: ## Create a tenant via the API. SLUG=<slug> NAME=<name> ADMIN_EMAIL=<email>
	@test -n "$(SLUG)" || (echo "Usage: make provision-tenant SLUG=sacco-four NAME='Sacco Four' ADMIN_EMAIL=admin@sacco-four.example.com"; exit 2)
	@TOKEN=$$(make -s platform-token); \
	curl -s -X POST http://$(API_HOST):$(API_PORT)/platform/tenants \
		-H 'Content-Type: application/json' \
		-H "Authorization: Bearer $$TOKEN" \
		-d '{"slug":"$(SLUG)","name":"$(NAME)","admin_email":"$(ADMIN_EMAIL)"}' \
		| python -m json.tool

tail-api: ## Tail the most recent uvicorn output file in /tmp/
	@tail -F $$(ls -t /tmp/claude-*/tasks/*.output 2>/dev/null | head -1)

tail-worker: ## Tail the most recent celery worker output file in /tmp/
	@tail -F $$(ls -t /tmp/claude-*/tasks/*.output 2>/dev/null | head -1)
