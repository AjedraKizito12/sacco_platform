# ADR-002: Platform-User Impersonation Design

**Date:** 2026-06-02
**Status:** Accepted (Phase 1.7, sub-plans 02a + 02b)
**Deciders:** Liam / Claude
**Context:** ADR-001 (`2026-05-21-iam-architecture.md`) §7 mandated that cross-context access by platform users to tenant routes must go through `platform.support_impersonations`. That ADR named the table but did not specify the lifecycle, the token model, the audit semantics, or how downstream tenant code would see the actor identity. This ADR locks all of that in before 02b writes the HTTP integration.

---

## Decisions

### 1. Lifecycle: request → approve → mint → use → end/revoke

Five distinct states:

1. **request** — `POST /platform/impersonations` (02b) submits an `ApprovalRequest` with `operation_type="platform.start_impersonation"`. No `support_impersonations` row exists yet; only the pending approval.
2. **approve** — A checker calls `POST /platform/approvals/{id}/approve` (P1.7-01). `ApprovalService.approve()` invokes the executor, which inserts the `support_impersonations` row with `started_at=now()`, `expires_at=now()+IMPERSONATION_MAX_MINUTES`, and `approval_request_id=<id>`. Self-approval is rejected by `ApprovalService`. Quorum is configurable per env (`IMPERSONATION_DEFAULT_REQUIRED_APPROVALS`, default 1).
3. **mint** — `POST /platform/impersonations/{id}/mint-tenant-token` (02b). Lazily creates the shadow `tenant_users` row in the target tenant's schema (decision §3), then issues a standard tenant access+refresh token with the shadow user's `sub`. The token is a normal tenant JWT — no new claims, no audience change.
4. **use** — The platform user calls tenant routes with the minted token + `X-Tenant-Slug`. The existing `get_current_tenant_user_jwt` dep validates the token and returns the shadow `TenantUser`. Downstream code uses `user.id` (the shadow id) for `posted_by` / `recorded_by` etc. — those columns are plain UUID without FK constraints, so no integrity issues.
5. **end / revoke** — `DELETE /platform/impersonations/{id}` (02b, by the impersonator) sets `ended_at`. `POST /platform/impersonations/{id}/revoke` (02b, by another admin) sets `revoked_at`. Both deactivate the shadow `tenant_user` and revoke all its tenant sessions.

### 2. Maximum duration: 30 minutes, configurable

`IMPERSONATION_MAX_MINUTES` defaults to 30. Production may tune. Sessions auto-expire — no separate Celery beat job is required, because `expires_at > now()` is part of every `is_active` check.

### 3. Shadow tenant_users: lazy creation on first mint

Rather than rewriting `get_current_tenant_user_jwt` to handle a synthetic non-DB identity, we create a real `tenant_users` row per impersonation session:

- `email` = `f"imp.{impersonation_id.hex[:12]}@platform.local"` — guaranteed unique, clearly non-real, never collides with a real tenant user's address
- `full_name` = `<platform_user.full_name> + " (Platform Admin Impersonation)"`
- `is_active` = `true`
- `is_admin` = `true`
- `hashed_password` = `NULL` (cannot self-login)
- `impersonation_id` = the `support_impersonations.id` (new column, indexed where NOT NULL)

The shadow row is created **lazily on the first `mint-tenant-token` call** for this impersonation, and reused for subsequent mints during the same session. On `end` / `revoke`, `is_active` flips to `false` and the row stays for audit traceability.

**Trade-off:** an extra `tenant_users` row per impersonation session, with the `impersonation_id` column marking it as a shadow. The portal's `/settings/users` list (P1.7-04) MUST filter `impersonation_id IS NULL` so shadows don't leak into the operator's UI.

### 4. Audit identity: actor_type='tenant_user', actor_id=shadow_id, impersonation_id=link

Every audit_log row written during an impersonated request gets:
- `actor_type = 'tenant_user'` (NOT `'platform_user'`)
- `actor_id = <shadow_tenant_user.id>`
- `actor_label = "<platform_user.email> (impersonating)"`
- `impersonation_id = <support_impersonations.id>` (new column on `audit_log`)

This makes the audit trail uniformly tenant-actor-shaped (no `posted_by` resolves to a non-existent tenant_user), while `impersonation_id` provides instant traceability back to the real platform actor. The portal's audit viewer (sub-plan 31 of Portal v1) joins on `impersonation_id` to resolve and display the real actor identity.

The mechanism: 02b extends `AuditableMixin._actor_context` to read `impersonation_id` from structlog contextvars. The tenant JWT dep (extended in 02b) binds `impersonation_id` to contextvars when the resolved tenant_user has a non-null `impersonation_id` column.

### 5. Tokens: regular tenant JWT with shadow user as `sub`

No new claim. No new audience. No new TTL. The shadow user has a `tenant_users.id` like any other; the minted token has `sub=<that id>`, `aud=tenant:<slug>`, normal access TTL (15 min). The shadow lives in the tenant schema, so the existing `get_current_tenant_user_jwt` dep resolves it transparently.

Re-mint within the impersonation window is unrestricted: the impersonator can call `mint-tenant-token` repeatedly to get fresh access tokens (or use the refresh token flow). Every mint creates a new tenant session row tied to the same shadow user.

### 6. Self-approval still forbidden

`ApprovalService.approve` already rejects `actor_user_id == request.requested_by`. This applies to impersonation requests too — the requester cannot approve their own request even if they hold a sufficiently privileged role.

### 7. Listing impersonations is restricted

- `GET /platform/impersonations/active` (mine) — any authenticated platform user.
- `GET /platform/impersonations/all` (system-wide) — admin role or above (P1.7-05).

Both list endpoints exclude shadow `tenant_users` from any tenant-user listing API.

### 8. Failure modes

| Scenario | Behaviour |
|----------|-----------|
| Executor fails inserting `support_impersonations` | `ApprovalService._execute` catches; request `status='execution_failed'`; no row, no shadow user. The maker can request again. |
| Mint called before approval | 404 — no impersonation row exists with that id. |
| Mint called after expiry / revoke / end | 410 Gone (02b). |
| Tenant request with an expired impersonation token | 401 — the shadow user's tenant session is revoked when `end` / `revoke` runs. Tokens still valid until 15-min expiry returns 401 from the JTI check. |
| Maker tries to revoke their own session | Returns 200; treated as `end()` (their `ended_at` is set). Audit captures the action. |

### 9. What is explicitly NOT in scope (Phase 1.7)

- **MFA step-up for impersonation start.** Future hardening; the maker-checker quorum is the gate in v1.
- **Per-tenant policy on impersonation** (e.g., a tenant opting out). Tenants are notified via audit log; opt-out is a future control.
- **Read-only impersonation mode.** v1 impersonations have full tenant_user privileges of the shadow user (i.e., `is_admin=true`). A read-only mode would require a permission flag on the shadow user; deferred.
- **Cross-tenant impersonation in a single session.** A session is scoped to one tenant. Operating across tenants requires multiple sessions.

---

## CLAUDE.md Contracts Added (02a)

See the Impersonation contracts subsection in CLAUDE.md (added in Task 10 of this sub-plan). The full set of contracts is augmented in 02b once the HTTP and audit-mixin pieces land.

## Consequences

- Phase 1.7 can ship 02a as a backend-only, schema-only PR. The data layer becomes correct and reviewable in isolation.
- 02b becomes a focused PR about cross-context auth wiring with no schema surprises.
- Portal sub-plan 14 (Tenants edit/suspend + impersonation entry point) has a clean API contract once 02b lands.
- ADR-001 §7 is now implementable. Future hardening (MFA step-up, read-only mode, per-tenant opt-out) can extend this design without rewriting it.
