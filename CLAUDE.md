# SACCO Platform — Project Context

## What this is
A multi-tenant SACCO (Savings and Credit Cooperative) core banking platform.
Schema-per-tenant on PostgreSQL. Each tenant SACCO gets its own schema.

## Tech stack (FIXED — do not substitute)
- Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Alembic
- PostgreSQL 16, Redis 7, RabbitMQ 3.12, Elasticsearch 8
- Celery (workers + beat), structlog, Pydantic v2
- Docker Compose for local dev
- pytest, pytest-asyncio, factory-boy
- ruff + mypy (strict) — non-negotiable

## Architectural rules (do not violate)
1. Modular monolith. Modules live under app/modules/<name>/.
2. Cross-module communication via service interfaces or domain events, NEVER direct model imports.
3. Every monetary state change posts a balanced double-entry journal in the same DB transaction.
4. Financial tables (account_transactions, journal_entries, journal_lines) are append-only. Reversals = new entries.
5. Money is stored as integer minor units or DECIMAL(19,4). NEVER float.
6. Multi-tenancy via Postgres schemas. Tenant resolved by middleware, applied via SET LOCAL search_path.
7. Maker-checker required for: loan approvals, transaction reversals, manual GL entries, fee waivers, member status changes.
8. Every sensitive operation writes to audit_log with before/after JSON.
9. Outbox pattern for events to RabbitMQ. Never publish directly from business code.
10. All product terms (interest rates, fees) are SNAPSHOTTED onto loans/accounts at creation. Never reference live config for historical records.

## Bounded contexts (build in this order)
1. core (tenancy, db session, security, audit, events, maker-checker)
2. platform_ (tenants, platform users)
3. iam (users, roles, permissions inside tenants)
4. ledger (chart of accounts, journal posting)
5. members (lifecycle, KYC fields)
6. shares (share capital)
7. savings (products, accounts, manual transactions)
8. fees (membership, annual subscription, assessment job)
9. credit (products, applications, loans, schedules, repayments, guarantors)
10. reporting (statements, trial balance, loan portfolio)

## Current scope (starting build)
- Manual transaction capture only (no payment integrations)
- No external compliance integrations
- No mobile/USSD channels yet
- Single currency per tenant (UGX default), but design assumes multi-currency

## Conventions
- All async functions and database calls. No sync DB code.
- Pydantic schemas in schemas.py, SQLAlchemy models in models.py, business logic in service.py, FastAPI router in api.py.
- Test every service method. Integration tests use a real Postgres in Docker.
- Migrations: alembic/platform/ for shared schema, alembic/tenant/ for per-tenant schema.
- All tenant model tables declare NO schema; resolved at runtime via search_path.
- Platform tables: __table_args__ = {"schema": "platform"}.
- Idempotency keys on any operation that could be retried.

## What NOT to do
- Do not introduce ORMs other than SQLAlchemy.
- Do not store balances as the source of truth — derive from journal lines.
- Do not delete or update rows in financial tables.
- Do not bypass maker-checker by adding "admin override" shortcuts.
- Do not hardcode tenant logic; everything is multi-tenant from day one.
- Do not add new top-level dependencies without justification in commit message.

## Files Claude should always read for context
- CLAUDE.md (this file)
- app/core/ (any time touching cross-cutting concerns)
- The module's own models.py + service.py before editing that module

## Core module contracts (do not violate)
- Direct RabbitMQ client usage is forbidden outside `app/core/outbox/`. All events go through `EventPublisher.publish()`.
- All event consumers must check `processed_events` before acting. At-least-once delivery is the contract.
- Approvable operations must be registered via `@approval_executor` and invoked through `ApprovalService`. Direct execution paths for approvable operations are forbidden.

## Platform_ module contracts (do not violate)
- Tenant provisioning is asynchronous. POST /platform/tenants returns 202 with a status_url. Clients poll GET /platform/tenants/{id}. Direct schema creation outside the provisioning workflow is forbidden.
- Platform auth is a stub. get_current_platform_user validates X-Platform-Actor-ID against platform.platform_users but does NOT authenticate. Production deployment requires PLATFORM_AUTH_MODE != stub (enforced at startup).
- Do not add password handling, login routes, or /me endpoints to platform_. Those belong in IAM.
- Platform users acting inside a tenant context send both X-Platform-Actor-ID and X-Tenant-Slug. Audit records actor_type='platform_user' and actor_id=<platform_user.id> in the tenant audit_log.
- run_tenant_migrations() in app/platform_/provisioning/migrations.py is the canonical way to run tenant Alembic migrations. Do not use subprocess or direct psycopg2 calls for this.