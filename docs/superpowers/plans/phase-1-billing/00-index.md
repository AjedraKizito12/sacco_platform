# Phase 1 — Billing & Subscription Management: Sub-Plan Index

> Sub-plans for the billing module, following the same task-by-task structure
> as the reporting build (`docs/superpowers/plans/reporting/`).
>
> **Master roadmap reference:** `docs/superpowers/plans/saas-launch-roadmap.md`
> §5 Phase 1.
>
> **Integration branch:** `feat/phase-1-billing` (this branch).
> Each sub-plan implementation lives on a topic branch off this integration
> branch and is reviewed via PR before merging back.

## Module goal

Convert the platform from "tenants are provisioned for free" to "tenants pay
to use the platform." Subscription state on `platform.tenants` becomes the
access gate that downstream phases (2 admin portal, 6 rate limits,
7 offboarding) build on. Offline-only payment processing in v1 with a
`PaymentProcessor` interface that future Flutterwave / Stripe / MoMo
implementations slot into without touching the service layer.

## Sub-plan sequence

| # | Sub-plan | Goal | Est | Blocks |
|---|---|---|---|---|
| 01 | Schema, models, schemas | Migration 014, 5 SQLAlchemy classes + ALTER `platform.tenants`, Pydantic types | 3d | 02–06 |
| 02 | Processor interface + SubscriptionService | `PaymentProcessor` ABC, `OfflineProcessor`, `SubscriptionService` (assign/cancel/transition) | 4d | 03–06 |
| 03 | InvoiceService + PaymentService | Invoice generation (with line items + numbering), invoice voiding, payment recording, confirmation | 3d | 04–06 |
| 04 | Maker-checker executors + subscription gate | `@approval_executor` wiring for record_payment / void_invoice / cancel_subscription; subscription-state middleware in `get_tenant_session` | 3d | 05–06 |
| 05 | API endpoints + invoice PDF | All HTTP endpoints (platform admin + tenant), Jinja2 invoice template, WeasyPrint render | 3d | 06 |
| 06 | Beat jobs + integration + docs | 4 nightly Celery tasks, `celery_app.py` wiring, end-to-end test, runbooks, CLAUDE.md contracts | 3d | — |

**Total:** 19 working days ≈ 3 calendar weeks (per the roadmap's L estimate).

## Architectural decisions locked across sub-plans

- **Schema-level placement:** every table lives in the `platform` schema.
  Tenants are charged by the platform; the tenant schema never sees billing
  state. The only tenant-schema impact is *behaviour* (the subscription gate
  middleware rejects requests against suspended tenants).
- **Money type:** `Numeric(19, 4)`. Never float. UGX-locked in v1 (the
  `currency` column exists for forward compatibility).
- **State machine:** subscription state lives on
  `platform.subscriptions.status` AND a denormalized
  `platform.tenants.subscription_status`. The denormalized column is what
  the middleware reads on every request. The Service-layer transition
  helpers write both atomically.
- **Audit + maker-checker:** every mutating billing operation either inherits
  `AuditableMixin` (for direct ORM writes) or goes through
  `ApprovalService` (for maker-checker operations). No silent writes.
- **Idempotency:** every operation that could be retried carries an
  `idempotency_key`. The maker-checker layer already handles this for
  approve-once semantics; service-layer methods enforce it for payment
  recording.
- **Processor abstraction:** `PaymentProcessor` ABC in
  `processors/base.py`. `OfflineProcessor` is the default. Stub modules
  (`flutterwave.py`, `stripe.py`, `momo.py`) exist with `NotImplementedError`
  so the module graph is in place for future work.

## Conventions

- Mirror the reporting module's file layout (`app/platform_/billing/`
  flat package + a `services/` subpackage + a `processors/` subpackage).
- Tests live under `tests/platform_/billing/`.
- Each sub-plan branch is named `feat/phase-1-billing/0X-short-title` and
  PRs into `feat/phase-1-billing`.
- Each sub-plan ships its own Alembic migration when it introduces tables.
  (SP01 owns 014; later sub-plans may add small ALTERs as 014a/015 if
  needed — decide at the time.)
- Each sub-plan ends with a `git commit -m "feat(billing): ..."`. The
  integration branch accumulates these.

## Out of scope for Phase 1

These are listed in the roadmap as deferred and stay deferred here:

- Real payment processor integrations (Flutterwave / Stripe / MoMo) —
  the interface is stubbed; real implementations land post-launch.
- Tenant-facing invoice download by tenant users (Phase 2 admin portal
  exposes it; the tenant-side endpoint exists per the API table, but a
  member-facing UI is not part of Phase 1).
- Multi-currency. UGX-only.
- Tax handling beyond the column. `amount_tax` exists; tax computation is
  manual via admin until a post-launch milestone.

## How to use these sub-plans

1. **Before starting a sub-plan**: re-read this index and the relevant
   sub-plan in full.
2. **Branch**: cut from `feat/phase-1-billing` (this branch). Name as
   `feat/phase-1-billing/0X-...`.
3. **Implementation**: follow the checkbox steps in the sub-plan. Each
   sub-plan declares its REQUIRED SUB-SKILL up top
   (`superpowers:subagent-driven-development` for all six).
4. **PR**: when the sub-plan's tests pass, open a PR back into
   `feat/phase-1-billing`. The integration branch accumulates commits.
5. **After all six**: open a single PR `feat/phase-1-billing` → `main`.
