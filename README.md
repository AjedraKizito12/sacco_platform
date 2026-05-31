# SACCO Platform

Multi-tenant SACCO (Savings and Credit Cooperative) core banking platform.
Schema-per-tenant on PostgreSQL — each tenant gets its own Postgres schema
inside one database; the API resolves the schema from a request header.

## Status

Reporting (#10) is the last bounded context in the build sequence and is
complete. All ten contexts are shipped:

  1. core (tenancy, db session, security, audit, events, maker-checker)
  2. platform_ (tenants, platform users)
  3. iam (users, roles, permissions inside tenants)
  4. ledger (chart of accounts, journal posting)
  5. members (lifecycle, KYC)
  6. shares (share capital)
  7. savings (products, accounts, transactions)
  8. fees (membership, annual subscription, assessment)
  9. credit (products, applications, loans, repayments, write-off, restructuring)
 10. reporting (trial balance, loan portfolio, income statement, savings
     statement, fee collection)

CI gates: `ruff check`, `mypy`, the outbox import boundary, the credit
snapshot-write boundary. The test suite is 594 tests.

## Stack

  - Python 3.11+
  - FastAPI, SQLAlchemy 2.0 async, Alembic
  - PostgreSQL 16, Redis 7, RabbitMQ 3.12, Elasticsearch 8
  - Celery (workers + beat)
  - Pydantic v2, structlog
  - Pytest, ruff, mypy (strict)
  - Docker Compose for local infra

## Running locally

A `Makefile` surfaces the common ops. From the repo root:

```bash
make up                # docker compose up -d postgres redis rabbitmq elasticsearch postgres-test
make migrate           # run platform alembic migrations against the dev DB
make api               # uvicorn on http://127.0.0.1:8001
make worker            # Celery worker (registers every @celery_app.task)
```

Then in another terminal:

```bash
# Provision a tenant via the API (synchronous; the worker picks it up)
make provision-tenant SLUG=sacco-one NAME='Sacco One' \
    ADMIN_EMAIL=admin@sacco-one.example.com

# Seed the demo data set (1 member, 1 savings account + 3 txns, 1 disbursed
# loan with snapshot balances, 1 paid membership fee + collection,
# 6 balanced journal entries / 12 journal lines)
make seed-demo TENANT=tenant_sacco_one

# Materialize the five report types for January 2026
make materialize-reports TENANT=tenant_sacco_one PERIOD_END=2026-01-31

# Hit a report
curl -s "http://127.0.0.1:8001/reporting/trial-balance?as_of=2026-01-31&format=json" \
    -H "X-Tenant-Slug: sacco-one" \
    -H "X-Tenant-Actor-ID: $(uuidgen)" | python -m json.tool
```

`make help` lists every target.

## Environment

`.env` is required and not checked in. The variables that matter for
local dev (mirroring the values used in this repo's setup):

```ini
DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5432/sacco
REDIS_URL=redis://localhost:6379/0
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
ELASTICSEARCH_URL=http://localhost:9200

APP_ENV=development
APP_SECRET_KEY=<32-byte secret>
JWT_KEK=<base64-encoded 32-byte key-encryption-key>

PLATFORM_AUTH_MODE=jwt          # production posture; 'stub' allowed only outside production
TENANT_AUTH_MODE=jwt
PLATFORM_BOOTSTRAP_EMAIL=admin@platform.example.com
```

The first time the platform schema is migrated, a bootstrap superuser
is seeded with the `PLATFORM_BOOTSTRAP_EMAIL` and a NULL
`hashed_password`. Set one via:

```python
from app.modules.iam.passwords.service import hash_password
# UPDATE platform.platform_users SET hashed_password = ... WHERE email = ...
```

The password must be at least 12 characters.

## Architectural rules

CLAUDE.md is the authoritative contract. Quick recap of the
non-negotiables:

  - Modular monolith. Cross-module communication via service interfaces
    or domain events. Never direct model imports.
  - Every monetary state change posts a balanced double-entry journal in
    the same DB transaction.
  - Financial tables are append-only. Reversals are new entries.
  - Money: `DECIMAL(19,4)` or integer minor units. Never `float`.
  - Tenant isolation via Postgres schemas. The middleware resolves the
    tenant from `X-Tenant-Slug` and applies `SET LOCAL search_path`.
  - Maker-checker required for loan approvals, transaction reversals,
    manual GL entries, fee waivers, member status changes, loan
    write-offs above the product's `write_off_threshold`.
  - Every sensitive operation writes to `audit_log` with before/after
    JSON.
  - Outbox pattern for domain events to RabbitMQ. Business code never
    publishes directly.
  - Product terms (interest rates, fees) are SNAPSHOTTED onto loans /
    accounts at creation. Historical records never reference live config.

## Tests

```bash
make test                  # full suite (~4 minutes against the test DB)
make test-fast T=tests/modules/reporting/test_trial_balance.py
make lint                  # ruff
make mypy                  # mypy strict
make ci                    # everything CI runs locally
```

The test DB runs on `postgres-test` (5433) per `docker-compose.yml`. The
test session in `tests/conftest.py` creates and drops `tenant_test`,
`platform` schemas on each pytest run.

For tenant-scoped routes the test pattern (in stub auth mode) is:

  1. Seed a `tenant_users` row (the `tenant_actor_id` fixture in
     `tests/conftest.py` does this).
  2. Pass `X-Tenant-Slug` and `X-Tenant-Actor-ID` on every request.
  3. The route's `CurrentTenantUser` dependency resolves the user from
     the actor-id header and binds the structlog context, so
     downstream `AuditableMixin` writes pick up the actor.

## Reporting

All five report endpoints share the same shape:

  - Each runs nightly at 01:00 UTC via Celery beat (see
    `app/modules/reporting/beat.py`).
  - Materialization writes ReportRun + N summary rows. The endpoint
    reads the latest successful run for the requested window, never
    recomputes.
  - Three response formats: `?format=json` (default), `?format=pdf`,
    `?format=csv`.
  - `GET /reporting/runs` lists recent runs across all five report
    types.

Trigger a single materialization on demand:

```bash
celery -A app.workers.celery_app call \
    app.modules.reporting.beat.materialize_trial_balance
```

## Folder layout

```
app/
  core/         # cross-cutting concerns (db, audit, outbox, security)
  platform_/   # platform-level (tenants, platform users, provisioning)
  modules/     # one folder per bounded context
    iam/       # users, sessions, JWT, keys
    ledger/    # GL accounts + journal entries
    members/   # member lifecycle
    shares/    # share capital
    savings/   # savings accounts
    fees/      # fee types + assessments + collections
    credit/    # loan products + applications + loans + ...
    reporting/ # the five report types
  workers/     # Celery app + beat schedule
docs/
  superpowers/specs/  # design specs
  superpowers/plans/  # per-module implementation plans
alembic/
  platform/    # platform-schema migrations
  tenant/      # tenant-schema migrations (run by provisioning task)
scripts/
  check_snapshot_writes.sh
  migrate_all_tenants.py
tests/
  ...
```
