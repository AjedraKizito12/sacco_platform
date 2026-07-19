# Product

## Register

product

## Users

SACCO platform operators (platform superusers/admins/finance/support), SACCO
staff (administrators, managers, accountants, tellers), and SACCO members.
Staff use the admin portal eight hours a day as an operational financial tool;
their mistakes cost money. Members use a lighter self-service portal to check
savings, shares, loans, and statements.

## Product Purpose

A multi-tenant SACCO (savings and credit cooperative) core banking platform.
The admin portal (Next.js, `admin/`) is a pure client of the FastAPI backend:
tenant management, billing, members, savings, credit, ledger, approvals,
audit, notifications. Success means operators complete high-volume financial
workflows quickly and without errors, and every sensitive action is auditable.

## Product Scope

SACCOs (savings & credit cooperatives) are member-owned financial institutions.
This platform runs the full back office for many SACCOs at once: each tenant
SACCO gets an isolated Postgres schema, and the same deployment serves the
platform operator, every SACCO's staff, and every SACCO's members.

### Audiences & surfaces

- **Platform operators** (superuser / admin / finance / support) — a
  back-office portal for provisioning and running SACCO tenants: tenant
  lifecycle, billing & subscriptions, platform users, cross-tenant approvals,
  audit, notifications config, KYC verification, support impersonation, and a
  platform-wide search + dashboard.
- **SACCO staff / operators** (tenant users, role-scoped) — the operator
  portal: the day-to-day financial tool for members, shares, savings, fees,
  credit, the ledger, reports, tenant-scoped approvals, and audit. Used eight
  hours a day; mistakes cost money.
- **SACCO members** — a lighter self-service portal: view savings, shares,
  loans, fees, and download consolidated statements. Members may submit KYC and
  apply for a loan; everything else is read-only.

### Functional capabilities (bounded contexts)

All ten core contexts plus billing, notifications, search, KYC, and
impersonation are complete and on `main` (see `CLAUDE.md` for per-module
contracts):

- **Tenancy & platform** — async tenant provisioning (202/poll), platform
  users, RS256 JWT auth, tenant lifecycle (suspend/reactivate/assign-plan).
- **IAM** — tenant + member auth, four-tier platform roles, sessions with
  immediate revocation, signing-key rotation, password reset, lockout.
- **Ledger** — chart of accounts and double-entry journal posting; the
  accounting source of truth.
- **Members** — member lifecycle and KYC fields; per-tenant KYC requirement
  sets, member-submitted KYC review.
- **Shares** — share-capital accounts.
- **Savings** — products, accounts, manual transactions, lien-aware available
  balance.
- **Fees** — membership / annual fees, assessment job, partial collection.
- **Credit** — applications, loans, repayment schedules, repayments,
  guarantors + liens, write-off (maker-checker), payroll batches,
  restructuring, and post-write-off recovery.
- **Reporting** — loan portfolio, income statement, savings statement, fee
  collection, and on-demand consolidated member statements (PDF/HTML).
- **Billing & subscriptions** (platform) — plans, subscriptions, invoices,
  payments, a subscription gate on tenant requests, and maker-checker for
  payment confirm / invoice void / subscription cancel.
- **Cross-cutting** — notifications framework (in-app + provider-pluggable
  email/SMS, null by default), global search (Elasticsearch, schema-isolated),
  SACCO + member KYC completion tracking, and audited support impersonation.

### Platform-wide guarantees

- **Multi-tenant** — schema-per-tenant, resolved by middleware via
  `SET LOCAL search_path`.
- **Double-entry & append-only** — every monetary state change posts a balanced
  journal in the same transaction; financial tables are never updated or
  deleted (reversals are new entries).
- **Maker-checker** — required for loan approvals, reversals, manual GL entries,
  fee waivers, member status changes, and the sensitive billing operations.
- **Auditable** — every sensitive operation writes before/after JSON to
  `audit_log`; impersonated actions are attributed to the operator.
- **Money is exact** — integer minor units or `DECIMAL(19,4)`, never float.
- **Snapshotting** — product terms (rates, fees) are frozen onto loans/accounts
  at creation; historical records never read live config.
- **Events via outbox** — domain events reach RabbitMQ through the outbox
  pattern; consumers are idempotent (at-least-once delivery).

### Delivery status (as of 2026-07-19)

- **Shipped:** all core banking modules; SaaS launch Phase 1 (billing),
  Phase 2 (operator portal), Phase 3 (notifications); member auth + member
  portal; KYC tracking; global search; support impersonation; and a Hetzner
  single-VPS **staging** deployment (Docker Compose + Caddy auto-TLS).
- **Next / not started:** Phase 4 backups & DR, Phase 5 observability, Phase 6
  rate limiting, Phase 7 offboarding, Phase 8 data portability, Phase 9
  external security assessment (see the roadmap in `CLAUDE.md`).

### Out of scope (current)

- Manual transaction capture only — no payment-gateway integrations yet
  (`OfflineProcessor` is the only live processor).
- No real email/SMS delivery (notifications ship with null/log providers).
- Single currency per tenant (UGX default); multi-currency columns exist but no
  logic keys off them.
- No external compliance integrations, no mobile / USSD channels.
- No production backups, observability, or rate limiting yet — staging is
  volume-only and not production-grade.

### Tech stack

Python 3.11 / FastAPI / SQLAlchemy 2.0 async / Alembic; PostgreSQL 16, Redis 7,
RabbitMQ 3.12, Elasticsearch 8; Celery workers + beat; Pydantic v2, structlog;
ruff + mypy (strict). Admin portal: Next.js 15 App Router + React 19,
TypeScript strict, Tailwind v4 + shadcn/ui, Playwright. Docker Compose for local
dev and staging.

## Brand Personality

Premium, professional, data-focused. Trustworthy, calm, precise. Approachable
without being playful; the interface recedes so the data reads first.

## Anti-references

- Consumer-fintech gradient flash: no gradients, glassmorphism, or decorative
  color. Monochrome-first; color is a signal, not decoration.
- Marketing-site whitespace: this is a dense operational tool, not a landing
  page. Whitespace serves data.
- Anything that hides state: silent failures, optimistic UI without
  confirmation, unlabeled icons.

## Design Principles

1. Clarity over decoration: numbers, statuses, and balances are the product.
2. Consistency everywhere: a component behaves identically in every module.
3. Data first: density is a feature; whitespace serves data.
4. Error prevention over error recovery: confirm dialogs, read-only fields,
   maker-checker flows; assume the user is tired and the data is sensitive.
5. Speed is a feature: server-side pagination, keyboard access, fast loads.

## Accessibility & Inclusion

WCAG AA. Every component keyboard-accessible. Tabular numerals for all
figures. Full contract detail lives in `docs/sacco-design-system-v2.md`
(canonical design system) and the portal contracts in `CLAUDE.md`.
