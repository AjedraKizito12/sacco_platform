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
- Platform auth uses RS256 JWT tokens when PLATFORM_AUTH_MODE=jwt (default). The stub (X-Platform-Actor-ID header, no crypto) requires PLATFORM_AUTH_MODE=stub and is forbidden in production. Do not add password or login logic to platform_/ — that belongs in IAM.
- Do not add password handling, login routes, or /me endpoints to platform_. Those belong in IAM.
- Platform users acting inside a tenant context send both X-Platform-Actor-ID and X-Tenant-Slug. Audit records actor_type='platform_user' and actor_id=<platform_user.id> in the tenant audit_log.
- run_tenant_migrations() in app/platform_/provisioning/migrations.py is the canonical way to run tenant Alembic migrations. Do not use subprocess or direct psycopg2 calls for this.

## IAM module contracts (do not violate)

- `PLATFORM_AUTH_MODE=jwt` and `TENANT_AUTH_MODE=jwt` are the production defaults. `stub` mode requires explicit opt-in and is forbidden when `APP_ENV=production`.
- `JWT_KEK` must be a base64-encoded 32-byte key-encryption-key. It is required at `Settings()` construction time whenever either auth mode is `jwt`. Never hardcode a KEK.
- `verify_boot_keys()` is called at startup when either auth mode is `jwt`. Do not remove or bypass this call.
- RSA signing keys are rotated by the Celery beat job (`rotate_signing_keys_if_due`). Do not create or delete signing key rows directly — use `KeyService`.
- Session revocation is immediate: `SessionService.is_jti_valid` checks Redis on every token decode. Do not skip this check in auth dependencies.
- Lockout is enforced only at the login endpoint (`PlatformAuthService.login`, `TenantAuthService.login`). Do not add lockout checks to the JWT dependency or to token refresh/logout.
- `reset_request()` must always return `None` regardless of whether the email exists. Never reveal user existence via this endpoint (anti-enumeration).
- Password reset tokens are single-use (15-minute TTL). The JTI is stored in Redis and consumed on `reset_confirm()`. Do not skip the Redis jti check when Redis is available.
- All auth operations write to `audit_log` via `write_platform_auth_event` / `write_tenant_auth_event`. Do not remove these calls. For failed login attempts, actor_id may be `None` (unknown user) — the nil UUID is used as record_id in that case.
- JWT token audiences: platform tokens use `aud="platform"`, tenant tokens use `aud="tenant:<slug>"`. A token issued for one tenant is rejected by another tenant's endpoints.
- `CurrentPlatformUser` is exported from `app.platform_.auth`. `CurrentTenantUser` is exported from `app.modules.iam.dependencies`. Do not import the underlying dependency functions directly into route handlers.

## Fees module contracts (do not violate)
- Fees module never writes to journal tables directly. Always via LedgerService.
- Fees module never mutates savings balances directly. Always via SavingsService.system_debit/system_credit.
- FeeAssessmentService.assess() is the only path to creating assessments. Never insert FeeAssessment rows directly.
- Assessment amount is snapshotted at creation. Changing fee_type.amount never retroactively changes assessed rows.
- system_debit and system_credit are not callable from HTTP routes (app/modules/*/api.py). CI should enforce this.
- Every savings_transactions row with source_module IS NOT NULL must also have source_id populated.
- Partial collection is a first-class outcome, not an error. Callers must handle shortfall_amount > 0 explicitly.
- System-initiated debit/credit: maker-checker is on the originating operation (e.g., assessment), not the financial movement.

## Credit module contracts (do not violate)
- Loan balance snapshot (`loans.outstanding_principal`, `accrued_interest`, `accrued_penalties`,
  `total_paid_principal`, `total_paid_interest`, `total_paid_penalties`, `total_written_off`) is
  the authoritative source for operational balance queries. GL is authoritative for
  accounting reports. The two are reconciled nightly by `reconcile_loan_snapshots`.
- All snapshot updates happen inside `app/modules/credit/services/` in a single transaction
  with the matching GL post. No other code path may UPDATE the snapshot columns.
  CI enforces this with a ripgrep check (see `scripts/check_snapshot_writes.sh`).
- Every `journal_line` produced by a credit operation must carry `sub_ledger_type='loan'`
  and `sub_ledger_id=loan.id`. Lines without `sub_ledger_id` are not queryable in the
  loan sub-ledger.
- Loan penalties are fees. The authoritative penalty record is `fee_assessments` with
  `target_type='loan'`. The credit module snapshots `accrued_penalties`; it does not store
  penalty history. There is no `loan_penalty_charges` table.
- Loan write-off is the only operation that decreases `outstanding_principal` without a
  member payment. It requires maker-checker with quorum=2 above the product's
  `write_off_threshold`.
- `SavingsService.record_external_credit` and `record_external_debit` are the only permitted
  paths for the credit module to create savings transaction rows. Never call savings
  `system_debit`/`system_credit` from the credit module.
- `CreditQueryService.find_loans_eligible_for_fee` is the only cross-module interface
  the fees engine may call into the credit module. No other direct calls between modules.
- Direct execution paths for `credit.write_off` (below `write_off_threshold`) and
  `credit.approve_application` are registered via `@approval_executor` in
  `app/modules/credit/executors.py`. Do not add alternate execution paths.

## Credit module v1b contracts (do not violate)
- Guarantor lien balance is always computed as SUM(current_lien WHERE is_active=true)
  from loan_guarantor_liens. Never cache this value outside a transaction.
- SavingsService.get_available_balance() must always subtract active liens before
  returning a withdrawable balance. Never bypass this for guarantors.
- Lien mutations (place_liens, adjust_liens, release_liens, reactivate_liens) must
  happen in the same DB transaction as the triggering financial operation (disbursement,
  repayment, write-off, recovery). Never update liens in a separate transaction.
- Payroll batch lines are applied one per commit. A failed line records status=error
  and does NOT roll back successfully applied lines.
- Restructuring never deletes installment rows. Mark is_superseded=true and write new rows.
- Write-off recovery does not require maker-checker. The cash receipt is the authorizing event.
- WeasyPrint is the only permitted PDF renderer in this module. Do not add alternative
  PDF libraries.

## Billing module contracts (do not violate)

- All billing tables live in the `platform` schema. The tenant schema never
  sees billing state. The only tenant-schema impact is *behaviour* (the
  subscription gate middleware in `get_tenant_session` — SP04 — rejects
  requests against suspended/cancelled tenants).
- `platform.subscriptions.status` is the authoritative subscription state.
  `platform.tenants.subscription_status` is a **denormalised** copy read by
  the request-time middleware. Every `SubscriptionService` transition writes
  BOTH rows in the same DB transaction. No other code path may update either
  column directly. CI should enforce that no service or executor outside
  `app/platform_/billing/services/` mutates `subscriptions.status` or
  `tenants.subscription_status`.
- `SubscriptionService.assign()`, `cancel()`, `reactivate()`,
  `transition_to_past_due()`, `transition_to_suspended()` are the only
  permitted state-transition methods. Direct `UPDATE platform.subscriptions
  SET status = ...` is forbidden.
- Money is `Numeric(19, 4)`. UGX-only in v1; the `currency` columns exist
  for forward compatibility but no code may key off them yet.
- `PaymentProcessor` interface lives in `app/platform_/billing/processors/base.py`.
  `OfflineProcessor` is the only concrete implementation in v1.
  `FlutterwaveProcessor`, `StripeProcessor`, `MobileMoneyProcessor` are
  intentional stubs — instantiating them raises `NotImplementedError`. Do not
  remove them; the module graph is part of the contract.
- `OfflineProcessor.initiate()` is a pure function — it never writes to the
  database. All DB writes for a payment happen in `PaymentService` (SP03),
  invoked via the maker-checker executor in SP04.
- Plan term snapshotting is intentionally NOT implemented in v1. Subscriptions
  reference plans by FK. If plan pricing changes, historical subscriptions
  reflect the new pricing on read. CLAUDE.md rule 10 (snapshotting product
  terms) applies to loans/savings; billing plans are explicitly out of scope.
  Add snapshot columns to `subscriptions` if regulatory audit later requires it.
- Maker-checker for `billing.record_payment`, `billing.void_invoice`,
  `billing.cancel_subscription` is wired in SP04 via `@approval_executor`.
  Direct calls to `PaymentService.confirm` / `InvoiceService.void` /
  `SubscriptionService.cancel(cancel_at_period_end=False)` are only allowed
  from the maker-checker executor module, never from HTTP route handlers.
- Invoice numbers are issued via per-year Postgres SEQUENCE named
  `platform.invoice_seq_YYYY`. Format: `INV-YYYY-NNNNNN` (6-digit
  zero-padded). The InvoiceService creates new yearly sequences lazily
  via `CREATE SEQUENCE IF NOT EXISTS`; do not hand-roll numbers.
- `InvoiceService.generate_for_subscription()` is the only path to
  creating an Invoice row. Direct `Invoice(...)` instantiation outside
  the service is forbidden. The function is idempotent on
  `(subscription_id, billing_period_start)`.
- v1 invoice line generation is **base price only** — one
  `InvoiceLineItem` per invoice with `quantity=1`, `unit_price =
  plan.base_price`. Per-user and per-member billing lines are
  intentionally out of scope; they would be zero-amount rows anyway
  because all v1 plans default both prices to 0. Implementations may
  add multi-line generation when a real-world plan requires it.
- `InvoiceService.void()` only voids invoices with `amount_paid = 0`.
  Voiding a partial/paid invoice is forbidden in v1; the caller must
  reverse payments first (payment reversal is post-launch work).
- `PaymentService.record()` is the only path to creating a Payment row.
  The function is idempotent on `idempotency_key` (DB-enforced via
  `uq_payments_idempotency_key`). Callers must supply a key ≥ 8 chars
  long (validated by `PaymentRecordIn`).
- `PaymentService.confirm()` is the only path to flipping a pending
  Payment to `confirmed` and applying the amount to the parent invoice.
  Self-approval (maker == checker) is rejected at the service level.
- `PaymentService.reject()` is the only path to flipping pending →
  rejected. Rejection reason is captured in the audit log (SP04
  executors write the entry), not on the Payment row.
- Overpayment is rejected: `confirm()` raises `OverpaymentRejected`
  if `amount_paid + new_amount > amount_total`. Partial payments are
  supported; the invoice transitions to `partial` until cumulative
  payments equal the total.