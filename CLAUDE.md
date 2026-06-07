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

## Bounded contexts — implementation status (as of 2026-06-02)

All 10 core bounded contexts are **complete and on `main`**:

| # | Module | Status |
|---|--------|--------|
| 1 | **core** | Complete — tenancy, DB session, security, audit, outbox, maker-checker |
| 2 | **platform_** | Complete — tenant provisioning (async 202/poll), platform users, RS256 JWT auth |
| 3 | **iam** | Complete — tenant users, roles, platform + tenant auth, sessions, key rotation, password reset, lockout |
| 4 | **ledger** | Complete — chart of accounts, double-entry journal posting |
| 5 | **members** | Complete — lifecycle, KYC fields |
| 6 | **shares** | Complete — share capital |
| 7 | **savings** | Complete — products, accounts, manual transactions, lien-aware available balance |
| 8 | **fees** | Complete — membership/annual fees, assessment job, partial collection |
| 9 | **credit** | Complete — applications, loans, schedules, repayments, guarantors, write-off, payroll batches, restructuring, recovery |
| 10 | **reporting** | Complete — loan portfolio, income statement, savings statement, fee collection (beat tasks + PDF/HTML) |
| — | **billing** (platform_) | Complete — plans, subscriptions, invoices, payments, maker-checker executors, subscription gate, PDF, 4 beat tasks |

## Current scope

- All 10 bounded contexts shipped. Ruff/mypy clean. Every tenant-scoped route requires `CurrentTenantUser`.
- Manual transaction capture only (no payment gateway integrations yet — `OfflineProcessor` is the only live processor).
- No external compliance integrations, no mobile/USSD channels.
- Single currency per tenant (UGX default). Multi-currency columns exist; no logic keys off them yet.
- **Next work: SaaS launch phases** — see section below.

## SaaS launch roadmap

Full spec: `docs/superpowers/plans/saas-launch-roadmap.md`

| Phase | What | Effort | Gates | Status |
|-------|------|--------|-------|--------|
| 1 | Billing & Subscription Management | L — 3 wk | closed beta | **Done** |
| 2 | Admin / Back-Office Portal (Next.js) | XL — 6 wk | closed beta | **Next** |
| 3 | Notifications Framework (NullProvider initially) | M — 2 wk | closed beta, runs parallel to P2 | Not started |
| 4 | Backups & Disaster Recovery (pgBackRest + PITR) | M — 2 wk | production launch | Not started |
| 5 | Observability & Monitoring (LGTM stack) | L — 3 wk | production launch | Not started |
| 6 | Rate Limiting & Abuse Protection | S — 1 wk | production launch (needs P5) | Not started |
| 7 | Tenant Offboarding & Retention | M — 2 wk | public launch (needs P1, P3) | Not started |
| 8 | Data Portability & Member Exports | M — 2 wk | public launch (needs P3) | Not started |
| 9 | External Security Assessment & Hardening | L — 3 wk | public launch (needs P1,P2,P4,P6) | Not started |

Sequential total: ~24 weeks. Parallel (5-person team): ~16 weeks.

### Phase 2 — Admin Portal key decisions
- **Stack**: Next.js 15 App Router + React 19, TypeScript strict (`noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`), Tailwind v4 + shadcn/ui, Playwright e2e.
- **Location**: new top-level `admin/` workspace (separate deployable, no Python code).
- **Auth**: consumes existing `/platform/auth/token` + `/auth/token` JWT endpoints. Refresh token in httpOnly cookie; access token in memory.
- **No new API endpoints** unless discovered necessary during build. One optional exception: `GET /platform/admin/dashboard-stats` aggregate endpoint.
- **Screen inventory** (28 screens across 7 nav groups): Tenants, Users, Billing, Approvals, Audit, Operations, Settings — full inventory in the roadmap doc.
- **Roles**: Platform Superuser / Admin / Finance / Support (4 tiers, enforced at API layer via `app/platform_/auth.py`'s `get_current_platform_user_with_role(role)` factory and the `CurrentAdmin` / `CurrentFinance` / `CurrentSupport` shortcuts).

### Phase 3 — Notifications key decisions
- Code lives in `app/core/notifications/` (cross-cutting).
- Ships with `NullNotificationProvider` and `LogNotificationProvider` only. No real email/SMS in v1.
- Outbox-pattern integration: `NotificationService.publish()` writes to outbox; Celery consumer dispatches.
- 9 initial event codes: `password_reset`, `maker_checker_pending/approved/rejected`, `invoice_issued/overdue`, `subscription_suspended`, `system_announcement`, `member_activated`.

### Admin portal contracts (do not violate)

A. The portal is a CLIENT of the existing FastAPI. No business logic.
B. **Zero new API endpoints in Phase 2.** All backend additions ship in Phase 1.7. If a sub-plan thinks it needs a new endpoint, stop and surface.
C. Access token in memory. Refresh token in httpOnly Secure SameSite=Strict cookie. Never `localStorage`, never `sessionStorage`, never plain cookies.
D. UI permission gating is UX only. API enforces.
E. Strict CSP. No `dangerouslySetInnerHTML`. No user-controlled HTML rendering.
F. Password reset tokens displayed in one-time modal (until Phase 3 email is wired). Never in URLs, query strings, or logs.
G. Subscription-gate responses: 402 → "Subscription past due — payment required" screen with link to billing; 403 (from gate) → "Account suspended — contact platform admin". Platform admin context is NOT gated.
H. Money via `<Money amount currency />`. Dates via `<FormattedDate>` / `<FormattedDateTime>` / `<AuditTimestamp>` / `<RelativeTime>`. Never raw `toLocaleString`.
I. All tables: TanStack Table via `@sacco/ui` DataTable. Server-side pagination, sort, filter. URL state via nuqs.
J. All forms: React Hook Form + Zod. Schemas in `@sacco/schemas`.
K. Maker-checker UI patterns: action buttons labeled "Request X" not "X" when they create approval requests; confirm dialog explicitly states "This creates an approval request, not executes"; pending-approval banner on records with open approvals; approval inbox shows quorum ("1 of 2").
L. `Idempotency-Key` auto-injected on all POST/PUT/PATCH/DELETE by the API client (UUID per user intent — same UUID across retries of the same form submission).
M. No client-side data fetching for initial render. Server components fetch via the typed client; client components mutate via TanStack Query.
N. Do NOT modify anything outside `admin/` except: `docker-compose.yml` (add admin service), `Makefile` (add `admin-*` targets), `CLAUDE.md` (append portal subsection, update Phase 2 stack to "Next.js 15"), `.gitignore` (admin entries). Backend code, alembic, docker/, scripts/, tests/, app/ stay untouched.
O. Notification bell renders empty state ("Notifications coming soon") until Phase 3 ships. Bell component accepts the future Phase 3 event-feed shape but is fed null/empty in v1.

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
- Tenant lifecycle endpoints (`PATCH /platform/tenants/{id}`,
  `POST .../suspend`, `POST .../reactivate`, `POST .../assign-plan`) are the
  ONLY HTTP paths to mutate `tenants.name`, `tenants.is_active`,
  `tenants.status`, `tenants.subscription_status`, or
  `tenants.current_subscription_id`. Direct UPDATE from anywhere outside
  `TenantService` (for name/status/is_active/subscription_status) or
  `SubscriptionService` (for current_subscription_id, set automatically by
  `assign`) is forbidden. The `tenant.suspend` maker-checker executor is the
  only path that calls `TenantService.suspend()`. `reactivate` is direct —
  no maker-checker — because re-enabling a tenant is a less destructive
  operation and the operator's intent is the authorising signal. Slug and
  schema_name remain immutable.
- `GET /platform/admin/dashboard-stats` (admin gate) returns a single aggregate
  view used by the portal dashboard. Cached in Redis for 60 seconds under key
  `dashboard:platform:stats`. The response shape (`DashboardStatsOut`) is the
  contract — adding new metrics is fine, renaming or removing existing keys
  requires a portal-side coordination. When Redis is unavailable, the
  endpoint falls through to a fresh computation; this is documented degraded
  behaviour, not a fault.
- The dashboard-stats Redis fallback path is **deliberately silent** — no
  logging on cache-decode failure, no logging on cache-write failure. Adding
  logs here would either spam during Redis flapping or stay quiet when needed.
  The portal's "Last updated" timestamp is the operator's signal of freshness.
- The dashboard-stats endpoint must NOT accept a `force_refresh` (or
  equivalent cache-bypass) query parameter. If the portal needs fresher data,
  shorten the TTL — do not give clients a knob that lets every dashboard
  reload skip the cache. Likewise, do not invalidate the cache on billing /
  tenant writes; the 60s TTL is the contract.
- The dashboard-stats MRR aggregation counts only subscriptions with status
  `active` or `trialing`. `past_due`, `suspended`, and `cancelled` do not
  count. If finance needs a different convention, expose a second metric
  rather than redefining this one.

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
- Tenant-user CRUD from a platform context lives under
  `/platform/tenants/{tenant_id}/users` (see `app/platform_/tenant_users_admin/`).
  These endpoints use the new `get_session_for_tenant_schema(tenant_id)`
  dependency in `app/core/db.py`. They are NOT subscription-gated — platform
  admins must be able to manage users regardless of tenant state.
- The list / get endpoints filter `impersonation_id IS NULL` so shadow
  tenant_users from the impersonation flow (P1.7-02) never appear in
  operator UI. The PATCH and password-reset endpoints also refuse to act
  on shadows (404).
- Admin-initiated password reset returns the HMAC reset token in the
  response body with a 24h TTL (vs 15min for self-service). The operator
  delivers it out of band until Phase 3 ships email. The same JTI/Redis
  consumption rules from `app/modules/iam/reset_tokens.py` apply; the
  user redeems via the existing `POST /auth/password-reset/confirm`.
- The `tenant_users_admin` endpoints gate on `CurrentAdmin` (admin or
  above), per the 4-tier role hierarchy.
- Platform user roles follow a strict hierarchy: `superuser > admin > finance > support`.
  Enforced by `get_current_platform_user_with_role(role)` in `app/platform_/auth.py`.
  `with_role("admin")` accepts admin and superuser; `with_role("finance")`
  accepts finance, admin, and superuser; `with_role("support")` accepts
  anyone authenticated; `with_role("superuser")` accepts superuser only.
- `is_superuser` is the deprecated mirror of `role='superuser'`. The
  `PlatformUserService` keeps the two in sync on create and update. Existing
  code that depends on `is_superuser` continues to work. New code should
  depend on `role` and the role-based dep shortcuts.
- Default gate policy on `/platform/*` routes: **support+ for read,
  admin+ for write**, with explicit exceptions:
  - `POST /platform/users` (create), JWT key admin routes, and
    `POST /platform/tenants` (create) require `CurrentSuperuser`.
  - Billing read endpoints require `CurrentFinance` (billing data is
    sensitive even read-only).
  - `POST /platform/billing/invoices/{id}/payments` (record) requires
    `CurrentFinance` — recording is the finance staff's job; approval
    requires `CurrentAdmin`.
  - Impersonation submit / active / detail / end / mint-token endpoints
    accept any authenticated platform user (the maker-checker quorum and
    impersonator-only checks provide the gate).
- New `/platform/*` routes should declare the required role explicitly at
  the dep level. Choose the lowest tier that is operationally correct —
  raising the bar later requires coordinating with portal permission UX.

## Impersonation contracts (do not violate)

### Data layer (from 02a, unchanged)

- `platform.support_impersonations` rows are created **only** by the
  `platform.start_impersonation` maker-checker executor. Direct insertion is
  forbidden. Direct UPDATE is forbidden except via `ImpersonationService.end()`
  and `ImpersonationService.revoke()`.
- `ImpersonationService.request()` is the only path to submitting a
  `platform.start_impersonation` approval. Reason must be at least 10 chars.
  Tenant must be active at request time.
- Self-approval is rejected by `ApprovalService.approve()`.
- Default required-approvals quorum is `IMPERSONATION_DEFAULT_REQUIRED_APPROVALS`
  (settings; default 1).
- `IMPERSONATION_MAX_MINUTES` (default 30) caps the session duration. Sessions
  expire automatically — no Celery beat job required.
- A row in `ended` or `revoked` state is terminal — the
  `ck_support_impersonations_not_both_ended_and_revoked` constraint disallows
  setting both. Re-impersonation requires a new approval cycle.
- `ApprovalService._execute` enriches the executor payload with
  `approval_request_id`. Executors must treat that key as reserved.

### HTTP + auth + audit (added in 02b)

- The `/platform/impersonations/*` router in
  `app/platform_/impersonations/api.py` is the only HTTP surface for the
  impersonation lifecycle. Direct service calls from outside this router
  or the executor are forbidden.
- `POST /platform/impersonations/{id}/mint-tenant-token` is the only path
  to obtain a tenant access token via impersonation. The endpoint is
  restricted to the original impersonator (platform_user_id match).
- Shadow `tenant_users` rows are auto-provisioned by
  `ImpersonationService.mint_tenant_token` on the first mint for an
  impersonation. They have `hashed_password=NULL`, `is_admin=true`,
  `is_active=true`, and `impersonation_id` set to the link. They cannot
  self-login (no password). They are reused for subsequent mints during
  the same impersonation.
- `tenant_users` listing endpoints (P1.7-04 / portal sub-plan 32) MUST
  filter `impersonation_id IS NULL` so shadows are invisible in operator UI.
- `tenant.audit_log` rows produced during an impersonated request carry
  `actor_type='tenant_user'`, `actor_id=<shadow_id>`,
  `actor_label='<platform_email> (impersonating)'`, and
  `impersonation_id=<support_impersonation.id>`.
  `platform.audit_log` is unchanged — it has no `impersonation_id` column.
- The tenant JWT and stub deps (`get_current_tenant_user_*`) both bind
  `impersonation_id` to structlog contextvars when the resolved tenant
  user has a non-null `impersonation_id` column. `AuditableMixin` reads
  the contextvar; do not bind `impersonation_id` from any other code path
  unless you are extending the audit trail intentionally.
- `DELETE /platform/impersonations/{id}` is restricted to the impersonator
  (`platform_user_id` match). `POST /platform/impersonations/{id}/revoke`
  is restricted to superuser (and admin once P1.7-05 ships). Both
  deactivate the shadow tenant_user and revoke all its tenant sessions
  in the same transaction.
- Token minting reuses the existing
  `KeyService.get_active_signing_key("tenant")` + `SessionService.create`
  + `tokens.service.encode_*_token` primitives. No bespoke crypto path.
- The minted token has `aud="tenant:<slug>"`, `sub=<shadow_tenant_user.id>`,
  `actor_type="tenant_user"`, and no `impersonation_id` claim. The audit
  trail is established at the dep layer (via contextvars) rather than at
  the token layer (via claims).
- HTTP responses for impersonation lifecycle endpoints:
  410 Gone — ended/revoked/expired; 409 Conflict — not yet active (no
  approval yet); 403 Forbidden — caller is not the impersonator;
  404 Not Found — id unknown.

See `docs/superpowers/decisions/2026-06-02-impersonation-design.md` for
the full design rationale.

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
- The maker-checker executors live in `app/platform_/billing/executors.py`:
  `billing.confirm_payment`, `billing.void_invoice`, `billing.cancel_subscription`.
  These are imported at app startup via `app/main.py` so the
  `@approval_executor` decorators register on boot. Do not remove the
  startup import — the registry is empty without it.
- Platform-scoped approval requests (created by `billing.*`, `platform_user.update_sensitive`,
  `tenant.retry_provisioning`, and future platform-scoped operations) are approved,
  rejected, listed, and cancelled via the `/platform/approvals/*` router in
  `app/modules/maker_checker/platform_api.py`. The tenant-scoped `/approvals/*`
  router in `app/modules/maker_checker/api.py` handles tenant-scoped requests
  only and does NOT see platform.approval_requests rows. `ApprovalService` is
  schema-agnostic — it picks the right model based on
  `session.sync_session.info["is_platform"]`, set by `get_platform_session`.
  Both routers reuse the same `SubmitApprovalRequest` / `ApprovalRequestOut` /
  `ApprovalActionRequest` / `RejectRequest` Pydantic schemas.
- There is no `billing.record_payment` executor. The maker action creates
  `Payment(status=pending)` + `ApprovalRequest(operation_type='billing.confirm_payment')`
  in one transaction (SP05 API). The checker's approval triggers the
  `billing.confirm_payment` executor, which calls `PaymentService.confirm()`.
- Payment rejection is paired at the API layer (SP05): the rejection endpoint
  calls `ApprovalService.reject(...)` and `PaymentService.reject(...)` in the
  same DB transaction. There is no rejection executor — `ApprovalService.reject()`
  alone would leave the `Payment` row stuck in `pending`.
- All billing executors are idempotent. They check the target row's status
  first and return success if already in the post-execution state. This
  protects against duplicate `ApprovalService.approve()` invocations from
  retries or beat-job interactions.
- The subscription gate runs inside `get_tenant_session` (in `app/core/db.py`)
  after schema resolution. It runs a single LEFT JOIN query
  (`platform.tenants` ⋈ `platform.subscriptions`) per request — fresh from
  Postgres, not cached. Schema_name continues to use the 5-minute Redis cache.
- Gate HTTP semantics are fixed contracts:
  `pending | trialing | active` → allow.
  `past_due` within `grace_period_ends_at` → allow.
  `past_due` past grace → **402 Payment Required**.
  `suspended | cancelled` → **403 Forbidden**.
  Changing any of these requires coordination with the Phase 2 admin portal.
- The gate applies to ALL tenant-scoped requests including GETs.
  `get_platform_session` is NOT gated — operators must be able to manage
  tenants in any state.
- Hard cancellation (`SubscriptionService.cancel(cancel_at_period_end=False)`)
  is only callable from the `billing.cancel_subscription` executor.
  Direct calls from HTTP handlers are forbidden. Soft cancellation
  (`cancel_at_period_end=True`) does not require maker-checker.
- HTTP API surface lives in `app/platform_/billing/api.py`, exposing two
  routers: `platform_router` at `/platform/billing/*` and `tenant_router`
  at `/billing/me/*`. Both are mounted from `app/main.py`. Do not add
  billing endpoints outside this file.
- `POST /platform/billing/invoices/{id}/payments` creates `Payment(pending)`
  and the matching `ApprovalRequest(operation_type='billing.confirm_payment')`
  in one DB transaction. The maker calls this; the checker approves via
  the generic `/maker-checker/approval-requests/{id}/approve` endpoint or
  rejects via `/platform/billing/payments/{id}/reject` (paired rejection).
- `POST /platform/billing/payments/{id}/reject` is the ONLY way to reject
  a pending payment. It pairs `ApprovalService.reject()` +
  `PaymentService.reject()` in one transaction. Using the generic approval
  reject endpoint alone leaves the Payment row stuck in 'pending'.
- `POST /platform/billing/subscriptions/{id}/cancel?mode=at_period_end`
  is a direct call (no maker-checker — soft cancel, reversible until period
  end). `?mode=immediate` goes through the maker-checker executor.
- `POST /platform/billing/invoices/{id}/void` always requires maker-checker.
  There is no direct void endpoint.
- Invoice PDFs are rendered on-demand at GET time via WeasyPrint. The
  template lives at `app/platform_/billing/templates/invoice.html`.
  `Invoice.pdf_storage_key` is reserved for a future caching layer and
  stays NULL in v1.
- Tenant-facing endpoints (`/billing/me/*`) read from the platform schema
  but enforce ownership in the handler via `tenant_id == current_user.tenant_id`.
  Cross-tenant access returns 404 (not 403) to avoid leaking row existence.
- `PaymentService.confirm()` accepts `confirmed_by: UUID | None`. The
  `billing.confirm_payment` executor calls it with `None` because
  `ApprovalService.approve()` has already enforced maker != checker.
  Direct callers (tests, scripts) should still pass the actual user UUID.