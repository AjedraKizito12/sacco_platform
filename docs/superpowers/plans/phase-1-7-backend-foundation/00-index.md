# Phase 1.7 — Backend Foundation for Portal · Plan Index

> **Status:** Drafted 2026-06-02. Companion to `2026-06-02-portal-v1-index.md`. Ships in parallel with Portal v1 Part A.
>
> **For agentic workers:** Each sub-plan listed below will be a full plan document under `docs/superpowers/plans/phase-1-7-backend-foundation/`. Use `superpowers:subagent-driven-development` for execution.

---

## 1. Goal

Ship the backend additions that Portal v1 depends on, so Portal v1 can be a true zero-new-endpoint client. Seven discrete sub-plans, all backend-only. Total effort ~3 weeks for one full-time backend engineer.

Each sub-plan ships:
- migrations (where schema changes)
- models / schemas / service additions
- HTTP endpoints
- maker-checker executors (where applicable)
- unit + integration tests with real Postgres
- CLAUDE.md contracts updates

## 2. Architectural principles (do not violate)

These extend the existing contracts in CLAUDE.md. Each sub-plan reads the relevant CLAUDE.md subsection before writing code.

A. **All new endpoints follow existing module conventions.** `models.py`, `schemas.py`, `service.py`, `api.py`. Tests under `tests/<module-path>/`.

B. **`ApprovalService` is schema-agnostic** (`app/modules/maker_checker/service.py:31-42`). It picks `PlatformApprovalRequest` / `TenantApprovalRequest` based on `session.sync_session.info["is_platform"]`. The new `/platform/approvals/*` router uses `get_platform_session` and gets platform-scoped requests for free.

C. **Auditable mixin is automatic** (`app/core/audit/mixin.py:123`). Every model mixing it gets audit_log writes on insert/update/delete. New models should mix it where the change deserves an audit trail. Service-level explicit `audit_svc.record(...)` calls are still required for non-DML events (state transitions, business decisions).

D. **Maker-checker executors register at import time** via `@approval_executor("operation_type")` (`app/modules/maker_checker/registry.py`). The executor module must be imported at startup in `app/main.py` (the existing `# noqa: F401` pattern) or the decorator never runs.

E. **Cross-schema endpoints (platform context, tenant data) require explicit search_path management.** Sub-plan 04 (tenant-user CRUD from platform context) is the only case in Phase 1.7 that crosses schemas. It uses a dedicated dependency `get_session_for_tenant_schema(tenant_id)` that loads the tenant by UUID, validates the schema_name, and yields a session with `SET LOCAL search_path TO <schema>, platform`. Never inline search_path manipulation in route handlers.

F. **JWT audience rules unchanged.** Platform tokens stay `aud=platform`, tenant tokens stay `aud=tenant:<slug>`. Sub-plan 02 (impersonations) introduces a new mint path that issues a `tenant:<slug>` token from a verified platform identity AND requires an active impersonation row before each tenant request. The audience and verification path stay the same; the only addition is the impersonation_id check in `get_current_tenant_user_jwt`.

G. **Audit log entries for impersonated tenant operations carry `impersonation_id`.** Sub-plan 02 adds the column to `tenant.audit_log` and updates `AuditableMixin` to populate it from structlog context vars when an impersonation is active.

H. **4-tier platform roles** (P1.7-05) supersede the binary `is_superuser` flag. The migration converts `is_superuser=true` → `role='superuser'` and drops `is_superuser` only AFTER all call sites are updated. The existing `CurrentSuperuser` dependency continues to work (it becomes a shortcut for `role='superuser'`).

I. **Tenant `is_admin` flag stays as-is.** Tenant RBAC v2 is a future roadmap item; sub-plan 04 only adds the platform-side endpoints to flip `is_admin`. No new tenant-side authorization tiers in Phase 1.7.

## 3. Files added or modified (overview)

```
alembic/platform/versions/
  008_support_impersonations.py            (P1.7-02)
  009_tenant_management_columns.py         (P1.7-03)  — optional contact_email, contact_phone, billing_address
  010_platform_user_roles.py               (P1.7-05)
alembic/tenant/versions/
  014_audit_log_impersonation_id.py        (P1.7-02)  — adds column to tenant.audit_log

app/modules/maker_checker/
  platform_api.py                          (P1.7-01)  — new platform-scoped /approvals router

app/platform_/impersonations/              (P1.7-02)
  models.py, schemas.py, service.py, api.py, executors.py

app/platform_/tenants/                     (P1.7-03)
  api.py                                   — PATCH, suspend, reactivate, assign-plan endpoints
  service.py                               — extend TenantService
  executors.py                             — tenant.suspend executor

app/platform_/tenant_users_admin/          (P1.7-04)  — new sub-module
  api.py, service.py, schemas.py

app/platform_/admin/                       (P1.7-07)  — new sub-module
  api.py, service.py, schemas.py

app/platform_/models.py                    (P1.7-05)  — add role column to PlatformUser
app/platform_/auth.py                      (P1.7-05)  — add role-tier dependency factories
app/modules/iam/dependencies.py            (P1.7-02)  — extend tenant JWT dep to honor impersonation tokens
app/core/audit/mixin.py                    (P1.7-02)  — populate impersonation_id from context vars

app/core/audit/
  api.py                                   (P1.7-06)  — new platform + tenant audit query routers
  schemas.py                               (P1.7-06)

app/main.py                                — mount the new routers, import executors

tests/...                                  — full coverage per sub-plan
docs/superpowers/decisions/
  2026-06-XX-impersonation-design.md       (P1.7-02)  — ADR for impersonation flow

CLAUDE.md                                  — append contracts subsections per sub-plan
```

## 4. Sub-plan list

### P1.7-01 — Platform Approvals API

- **Dependencies:** none — `ApprovalService` and `PlatformApprovalRequest` already exist
- **Complexity:** S (2 days)
- **Required reading:**
  - `app/modules/maker_checker/api.py` (existing tenant router — mirror its shape)
  - `app/modules/maker_checker/service.py` (the schema-agnostic ApprovalService)
  - `app/modules/maker_checker/models/platform.py` (PlatformApprovalRequest, PlatformApprovalAction)
  - `app/platform_/billing/api.py:404-460` (existing record_payment flow shows the platform-side submit pattern)
- **Files:**
  - Create: `app/modules/maker_checker/platform_api.py`
  - Modify: `app/main.py` (mount router)
  - Test: `tests/modules/maker_checker/test_platform_api.py`
- **Endpoints (new):**
  - `POST /platform/approvals` (submit) — though usually submit happens inside other services; this endpoint is for the rare case of operator-initiated approvals
  - `GET /platform/approvals` (filters: status, operation_type, requested_by)
  - `GET /platform/approvals/{id}` (detail with actions list)
  - `POST /platform/approvals/{id}/approve` (calls `ApprovalService.approve` against platform schema; self-approval rejected; quorum logic runs)
  - `POST /platform/approvals/{id}/reject` (calls `ApprovalService.reject` against platform schema; self-rejection rejected)
  - `POST /platform/approvals/{id}/cancel` (maker only; pre-action only)
- **Maker-checker executors registered (existing — these get unblocked):**
  - `billing.confirm_payment`
  - `billing.void_invoice`
  - `billing.cancel_subscription`
  - `platform_user.update_sensitive`
  - `tenant.retry_provisioning`
  - (after P1.7-03 lands) `tenant.suspend`
  - (after P1.7-02 lands) `platform.start_impersonation`
- **Verification:**
  - Unit tests covering each endpoint, including self-approval rejection and 404 on tenant-scoped IDs
  - Integration test: end-to-end billing payment confirmation flow (maker records payment → checker approves via this new endpoint → executor confirms payment → audit log reflects both actors)
  - ruff + mypy clean
- **CLAUDE.md addition:** under §"Billing module contracts", update the docstring reference from `/maker-checker/approval-requests/{id}/approve` to `/platform/approvals/{id}/approve` (correct the misleading docstring in `app/platform_/billing/api.py:413`).

### P1.7-02 — Impersonations + cross-context tenant access

Split into two sub-plans during scoping:

- **P1.7-02a** — Data layer + service + executor + ADR. Ships migrations, models, `ImpersonationService`, and the `platform.start_impersonation` maker-checker executor. After 02a merges, an approved impersonation creates a row in `platform.support_impersonations` but cannot yet be used to access tenant routes (no token mint, no JWT dep update). Reviewable as a backend-only PR.
- **P1.7-02b** — API + token mint + tenant JWT dep extension + AuditableMixin update + end-to-end cross-context test + CLAUDE.md contracts. Wires the data layer into HTTP. Ships the shadow tenant_user pattern (lazy creation on first mint), the `POST /platform/impersonations/{id}/mint-tenant-token` endpoint, the tenant JWT dep extension that binds `impersonation_id` to structlog contextvars, and the `AuditableMixin` change that writes `impersonation_id` onto every audit row produced under an impersonation session.

- **Dependencies:** 02a has none for the core schema; integrates with P1.7-01 for the maker-checker executor. 02b depends on 02a.
- **Complexity:** L (5 days total) — split as ~2.5 days each
- **Required reading:**
  - `docs/superpowers/decisions/2026-05-21-iam-architecture.md` §7 (impersonation requirement)
  - `app/modules/iam/dependencies.py:155-218` (`get_current_tenant_user_jwt` — needs extension)
  - `app/modules/iam/tokens/service.py` (token minting)
  - `app/modules/iam/sessions/service.py` (Redis-backed session JTI tracking)
  - `app/core/audit/mixin.py:42-56` (`_actor_context` reads from structlog context vars — impersonation_id added here)
- **Files:**
  - Create: `alembic/platform/versions/008_support_impersonations.py`
  - Create: `alembic/tenant/versions/014_audit_log_impersonation_id.py`
  - Create: `app/platform_/impersonations/__init__.py`, `models.py`, `schemas.py`, `service.py`, `api.py`, `executors.py`
  - Modify: `app/modules/iam/dependencies.py` (tenant JWT dep accepts impersonation tokens)
  - Modify: `app/core/audit/mixin.py` (populate impersonation_id from context vars)
  - Modify: `app/main.py` (mount router, import executors)
  - Create: `docs/superpowers/decisions/2026-06-XX-impersonation-design.md` (lock down design choices)
  - Test: `tests/platform_/impersonations/test_models.py`, `test_service.py`, `test_api.py`, `test_cross_context.py`
- **Schema:**
  ```sql
  platform.support_impersonations
    id                  uuid pk
    platform_user_id    uuid FK platform.platform_users(id)
    tenant_id           uuid FK platform.tenants(id)
    reason              text NOT NULL
    approval_request_id uuid FK platform.approval_requests(id)
    started_at          timestamptz NOT NULL
    expires_at          timestamptz NOT NULL                -- default now() + IMPERSONATION_MAX_MINUTES
    ended_at            timestamptz nullable                -- explicit end via DELETE
    revoked_at          timestamptz nullable                -- revocation by another admin
    revoked_by          uuid nullable FK platform.platform_users(id)
    check (ended_at IS NULL OR revoked_at IS NULL)

  tenant.audit_log
    ADD COLUMN impersonation_id uuid                        -- nullable; populated by mixin when active
  ```
- **Endpoints:**
  - `POST /platform/impersonations` — body: `{tenant_id, reason}`; creates an approval request via `ApprovalService.submit(operation_type="platform.start_impersonation", ...)`; returns the approval_request_id
  - `GET /platform/impersonations/active` — list active impersonations for current platform user
  - `GET /platform/impersonations/all` — list all active impersonations (admin/finance role only — gated by P1.7-05)
  - `DELETE /platform/impersonations/{id}` — end an impersonation session (maker can end their own; admin can end any)
  - `POST /platform/impersonations/{id}/mint-tenant-token` — once approved, mint a `aud=tenant:<slug>` token tied to this impersonation; token includes `impersonation_id` claim
- **Maker-checker executor:** `@approval_executor("platform.start_impersonation")` → flips approval to `executed`, creates the `support_impersonations` row, returns `{impersonation_id, expires_at}`
- **Tenant JWT dep extension:**
  - When token has `impersonation_id` claim, verify the impersonation row exists, is unexpired, not ended, not revoked
  - Bind `actor_type='platform_user'`, `actor_id=impersonation.platform_user_id`, `actor_label=platform_user.email`, `impersonation_id=impersonation.id` to structlog context vars
  - `AuditableMixin._actor_context` then reads `impersonation_id` from context vars and writes it on every audit row
- **Settings additions:** `IMPERSONATION_MAX_MINUTES` (default 30), `IMPERSONATION_DEFAULT_REQUIRED_APPROVALS` (default 1; configurable per env)
- **Verification:**
  - Unit tests for service methods (start, end, revoke, expiry check)
  - Integration test: platform user requests impersonation → approver approves → mint token → call `/members` with that token → audit log shows `actor_type=platform_user`, `impersonation_id=<id>` → end impersonation → next request 401
  - Negative tests: expired impersonation rejected; revoked impersonation rejected; cross-tenant token rejected (mint for tenant A, try to access tenant B)
- **CLAUDE.md addition:** new subsection §"Impersonation contracts (do not violate)" with the 5–6 hard rules from this sub-plan

### P1.7-03 — Tenant edit, suspend, reactivate, assign-plan

- **Dependencies:** P1.7-01 (for the suspend executor's approval flow)
- **Complexity:** M (3 days)
- **Required reading:**
  - `app/platform_/tenants/api.py` (existing — extend)
  - `app/platform_/tenants/service.py`
  - `app/platform_/billing/services/subscription_service.py:82-160` (SubscriptionService.assign — this is what assign-plan delegates to)
- **Files:**
  - Create: `alembic/platform/versions/009_tenant_management_columns.py` (only if contact_email/phone/billing_address are needed — discuss in sub-plan; may be skipped if name+slug is sufficient for v1)
  - Modify: `app/platform_/tenants/api.py`, `service.py`
  - Create: `app/platform_/tenants/executors.py` (suspend executor)
  - Modify: `app/main.py` (import executors)
  - Test: `tests/platform_/tenants/test_api_extended.py`
- **Endpoints:**
  - `PATCH /platform/tenants/{id}` — update name (and optional contact fields if migration adds them). Superuser or admin role.
  - `POST /platform/tenants/{id}/suspend` — body: `{reason}`. Maker-checker; executor flips `tenants.is_active=false` and `subscription_status=suspended`. Audit trail captures reason.
  - `POST /platform/tenants/{id}/reactivate` — direct (no MC). Admin role. Flips `is_active=true`. Subscription status returns to `active` only if a healthy subscription exists; otherwise stays `pending`.
  - `POST /platform/tenants/{id}/assign-plan` — body: `{plan_id, start_date}`. Delegates to `SubscriptionService.assign`. Direct (no MC — this is part of normal onboarding).
- **Maker-checker executor:** `@approval_executor("tenant.suspend")` → flips status, writes audit, publishes outbox event
- **Verification:**
  - Unit tests covering each endpoint
  - Integration test: assign plan → suspend (with MC) → reactivate → verify subscription state machine
  - Verify subscription gate (`app/core/db.py:_check_subscription_gate`) responds correctly: suspended tenant → 403 on tenant routes; reactivated → 200
- **CLAUDE.md addition:** under §"Platform_ module contracts", add: tenant lifecycle endpoints (PATCH/suspend/reactivate/assign-plan) are the only paths to mutate `tenants.is_active` and `subscription_status`; direct UPDATE forbidden.

### P1.7-04 — Tenant-user CRUD + admin-initiated password reset

- **Dependencies:** P1.7-05 (for role gating — admin role required for these endpoints)
- **Complexity:** L (4 days) — cross-schema work is the tricky part
- **Required reading:**
  - `app/modules/iam/tenant_users/models.py` (TenantUser shape)
  - `app/modules/iam/platform_auth/service.py` (existing password-reset flow — mirror but admin-initiated)
  - `app/core/db.py:127-175` (`get_tenant_session` — shows the search_path pattern; cannot be used directly because the route is in platform context with no slug header)
- **Files:**
  - Create: `app/platform_/tenant_users_admin/__init__.py`, `api.py`, `service.py`, `schemas.py`
  - Create: dependency `get_session_for_tenant_schema(tenant_id)` in `app/core/db.py` (loads tenant by UUID, SET LOCAL search_path)
  - Modify: `app/main.py` (mount router)
  - Test: `tests/platform_/tenant_users_admin/test_api.py`
- **Endpoints (all under `/platform/tenants/{tenant_id}/users`, admin role required):**
  - `GET /platform/tenants/{tenant_id}/users` — list tenant users
  - `POST /platform/tenants/{tenant_id}/users` — create new tenant user; returns user + one-time `password_reset_token` (single use, 24h TTL — extended for admin-initiated)
  - `GET /platform/tenants/{tenant_id}/users/{user_id}` — detail
  - `PATCH /platform/tenants/{tenant_id}/users/{user_id}` — update `is_active`, `is_admin`, `full_name`
  - `POST /platform/tenants/{tenant_id}/users/{user_id}/password-reset` — generate new token, return in response body. Replaces email delivery until Phase 3 ships.
- **Cross-schema dependency:** `get_session_for_tenant_schema(tenant_id: UUID)` is a FastAPI dependency that:
  1. Loads `platform.tenants` row by UUID (using a separate connection)
  2. Validates `schema_name` matches `^tenant_[a-z0-9_]{1,40}$`
  3. Opens a new session with `SET LOCAL search_path TO <schema_name>, platform`
  4. Audit context bound: `actor_type='platform_user'`, `actor_id=<current platform user>`, `acting_in_tenant_id=<tenant_id>`
- **Audit:** every tenant_users mutation made via these endpoints writes `tenant.audit_log` with `actor_type='platform_user'` and (when an impersonation exists from P1.7-02) `impersonation_id`. For non-impersonation admin actions, a new optional column `acting_in_tenant_id` on `platform.audit_log` (or denormalised) tracks the cross-tenant context. v1 keeps it simple: only `tenant.audit_log` rows; rely on `actor_type` to distinguish.
- **Verification:**
  - Unit tests cover each endpoint
  - Integration test: create tenant user via admin endpoint → returned reset token → use token via existing `/auth/password-reset/confirm` (with X-Tenant-Slug) → login as that user
  - Negative tests: cross-tenant access (create user in tenant A, try to PATCH them with tenant_id of tenant B in URL) returns 404
- **CLAUDE.md addition:** under §"IAM module contracts", add: tenant_user mgmt from platform context uses `get_session_for_tenant_schema(tenant_id)`; admin password-reset returns token in response body until Phase 3 ships email delivery.

### P1.7-05 — Platform user 4-tier roles

- **Dependencies:** none — but blocks P1.7-04 (which uses admin role)
- **Complexity:** M (3 days)
- **Required reading:**
  - `app/platform_/models.py:60-75` (PlatformUser)
  - `app/platform_/auth.py` (CurrentPlatformUser, CurrentSuperuser)
  - `app/platform_/users/api.py`, `service.py` (where role checks live)
- **Files:**
  - Create: `alembic/platform/versions/010_platform_user_roles.py`
  - Modify: `app/platform_/models.py` (add `role` column)
  - Modify: `app/platform_/auth.py` (add `get_current_platform_user_with_role(*roles)` dep factory, `CurrentAdmin`, `CurrentFinance`, `CurrentSupport` shortcuts; keep `CurrentSuperuser` working)
  - Modify: `app/platform_/users/api.py` (gate `POST /platform/users` on superuser+admin; existing PATCH stays superuser)
  - Modify: `app/platform_/users/service.py` (extend to set role on create/update)
  - Modify: `app/platform_/users/schemas.py` (add `role` to In/Out)
  - Modify: all `/platform/*` routes to assert minimum required role (default: support for read, admin for write)
  - Test: `tests/platform_/test_roles.py`, plus updates to existing tests
- **Schema:**
  ```sql
  ALTER TABLE platform.platform_users
    ADD COLUMN role text NOT NULL DEFAULT 'support'
    CHECK (role IN ('superuser','admin','finance','support'));
  UPDATE platform.platform_users SET role='superuser' WHERE is_superuser=true;
  -- is_superuser column stays for backwards compat in v1; can be dropped in a follow-up after audit
  ```
- **Role hierarchy (for `get_current_platform_user_with_role`):**
  - `superuser` > `admin` > `finance` > `support`
  - `with_role("admin")` accepts admin OR superuser
  - `with_role("finance")` accepts finance OR admin OR superuser (NOT support)
  - Optional: explicit list `with_role("finance", "support")` for case where finance and support both apply but admin doesn't
- **Verification:**
  - Unit tests for each role tier and endpoint
  - Migration tested up + down
  - Integration test: create user with role=finance → can access billing endpoints, blocked from tenant create
- **CLAUDE.md addition:** under §"IAM module contracts", add: platform user roles are `superuser > admin > finance > support`; enforced at API layer via `get_current_platform_user_with_role`; `is_superuser` boolean preserved for backwards compat but role is authoritative.

### P1.7-06 — Audit log query API (platform + tenant)

- **Dependencies:** none
- **Complexity:** M (3 days)
- **Required reading:**
  - `app/core/audit/models.py` (PlatformAuditLog, TenantAuditLog schemas)
  - `app/core/audit/mixin.py` (understand what gets written and when)
- **Files:**
  - Create: `app/core/audit/api.py` (two routers — platform and tenant)
  - Create: `app/core/audit/schemas.py` (AuditLogOut, AuditLogDetailOut, AuditLogFilters)
  - Modify: `app/main.py` (mount routers)
  - Test: `tests/core/audit/test_api.py`
- **Endpoints:**
  - `GET /platform/audit-log` (admin role) — filters: `actor_type`, `actor_id`, `table_name`, `operation`, `from_date`, `to_date`, `record_id`. Cursor pagination on `(occurred_at DESC, id)`.
  - `GET /platform/audit-log/{id}` (admin role) — detail with full before/after JSON
  - `GET /audit-log` (tenant user, admin role within tenant) — same filter shape, tenant-scoped via search_path
  - `GET /audit-log/{id}` — detail
- **Index usage:** existing indexes `ix_platform_audit_log_table_record` and `ix_platform_audit_log_occurred_at DESC` (mirrored for tenant) cover the typical filter patterns.
- **Verification:**
  - Unit tests cover filter combinations, pagination, empty result, large result
  - Integration test: perform a member status change (which writes audit) → query audit log via this API → before/after JSON renders correctly
- **CLAUDE.md addition:** under §"Core module contracts", add: audit log is queryable via `/platform/audit-log` (platform) and `/audit-log` (tenant); both require respective admin role.

### P1.7-07 — Dashboard stats aggregate endpoint

- **Dependencies:** P1.7-05 (admin role gate)
- **Complexity:** S (2 days)
- **Required reading:**
  - `app/platform_/tenants/service.py`, `app/platform_/billing/services/subscription_service.py`
- **Files:**
  - Create: `app/platform_/admin/__init__.py`, `api.py`, `service.py`, `schemas.py`
  - Modify: `app/main.py` (mount router)
  - Test: `tests/platform_/admin/test_dashboard_stats.py`
- **Endpoint:**
  - `GET /platform/admin/dashboard-stats` (admin role)
  - Response shape:
    ```python
    class DashboardStatsOut(BaseModel):
        tenants: dict[str, int]            # counts by status: {"active": 12, "suspended": 1, ...}
        subscriptions: dict[str, int]       # counts by status
        mrr: dict[str, Decimal]             # by currency: {"UGX": 12500000}
        invoices_outstanding: dict[str, int]  # counts by status: {"issued": 8, "overdue": 2, ...}
        invoices_amount_outstanding: dict[str, Decimal]  # by currency
        approvals_pending: int              # platform-scoped
        active_impersonations: int
        last_updated: datetime
    ```
  - All counts computed in a single aggregation query (or 2-3 small ones — does not justify N+1)
  - Cached server-side for 60 seconds (Redis) to avoid hammering on dashboard reload
- **Verification:**
  - Unit tests verify each statistic computed correctly against fixtures
  - Integration test: seed fixtures → call endpoint → assert all counts
- **CLAUDE.md addition:** none (no new contracts; existing rules cover this read-only aggregate).

## 5. Sequencing and parallelism

Within Phase 1.7, the sub-plans can be partially parallelised:

```
P1.7-01  Platform Approvals API   ────────┐
P1.7-05  Platform user roles      ───┐    │
                                     │    │
P1.7-02  Impersonations            ──┴────┤
P1.7-03  Tenant edit/suspend       ───────┤  (depends on P1.7-01 for suspend executor)
P1.7-06  Audit log query API       ───────┤
P1.7-07  Dashboard stats           ───────┴── (depends on P1.7-05 for admin gate)
P1.7-04  Tenant-user CRUD          ──────────── (depends on P1.7-05 for admin gate; cross-schema work)
```

A single backend engineer can ship in dependency order:
1. **Week 1**: P1.7-01 + P1.7-05 (parallel; both small/medium with no other deps)
2. **Week 2**: P1.7-02 (largest — impersonation) + P1.7-03 (tenant lifecycle)
3. **Week 3**: P1.7-04 (cross-schema tenant-user CRUD) + P1.7-06 (audit query API) + P1.7-07 (dashboard stats)

Total: **~3 weeks calendar time** for one backend engineer.

## 6. Cross-cutting concerns

- **Tests:** integration tests use the existing `tests/conftest.py` fixtures. Real Postgres in Docker (`make up` brings up `postgres-test` on port 5433). Tenant tests use the existing tenant-fixture pattern.
- **Migrations:** all 4 new platform migrations (008, 009, 010) and 1 tenant migration (014) follow the existing alembic/platform and alembic/tenant patterns. Each sub-plan tests its own migration up and down.
- **Auth modes:** all new endpoints work under both `PLATFORM_AUTH_MODE=stub` (tests) and `jwt` (production). Tests set `PLATFORM_AUTH_MODE=stub`/`TENANT_AUTH_MODE=stub` via `tests/conftest.py` (already in place).
- **Audit:** every mutation writes audit_log automatically via `AuditableMixin`. Service-level explicit audit records are still required for state transitions that aren't simple DML (e.g., impersonation start, role assignment).
- **Idempotency:** all POST endpoints accept and respect `Idempotency-Key` header where retries are plausible (impersonation request submission, tenant suspend, plan assignment). Existing patterns in `app/modules/savings/service.py` and `app/platform_/billing/services/payment_service.py` show the shape.

## 7. Standard verification criteria (every sub-plan)

1. **ruff clean:** `make lint`
2. **mypy strict clean:** `make mypy`
3. **All tests pass:** `make test`
4. **New tests have integration coverage** with real Postgres (not just unit tests)
5. **Migration is reversible** — tested with `alembic downgrade -1` then `upgrade head`
6. **OpenAPI captured fresh** — after merge, sub-plan 05 of Portal v1 re-runs the openapi capture to keep the codegen in sync
7. **CLAUDE.md contracts updated** if the sub-plan adds a new contract (rule of thumb: anything an outside engineer could violate without knowing it)
8. **No new top-level dependencies** unless justified in commit message (per CLAUDE.md "What NOT to do")

## 8. What happens next

1. **You review this index.** Approve, request changes, or split.
2. **First Phase 1.7 sub-plan dispatches** — likely P1.7-01 (smallest, unlocks billing payment confirmation in portal sub-plan 16). One fresh subagent, focused context.
3. **In parallel:** Portal v1 sub-plan 01 (workspace bootstrap) can dispatch immediately — it has zero Phase 1.7 dependencies.
4. **Each Phase 1.7 sub-plan after that** generated one at a time with your approval between each.

Stop. Awaiting your review.
