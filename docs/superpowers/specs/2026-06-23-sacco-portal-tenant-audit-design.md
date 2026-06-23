# SACCO Admin Portal — Tenant Audit Log (Phase 3g-3) Design

**Date:** 2026-06-23
**Phase:** 3 (SACCO Admin / tenant-operator portal), sub-plan g (dead-link fills), part 3 — Tenant audit log
**Status:** Approved

## Context

Phase 3g fills three dead tenant sidebar links scaffolded in Phase 2:
- **3g-1 Ledger** — `/ledger/accounts` — done (PR #50).
- **3g-2 Tenant approvals inbox** — `/approvals` — done (merge 0e123e2).
- **3g-3 Tenant audit** (this doc) — `/audit` — the LAST dead link.

Unlike 3g-1/3g-2, 3g-3 is **not** pure-client: the operator context has no
audit-log endpoint. SP19 shipped two **platform-gated** audit endpoints
(`GET /platform/audit-log`, `GET /platform/tenants/{id}/audit-log`, both
`CurrentAdmin`), but a SACCO operator viewing **their own** tenant's audit trail
needs a tenant-context route. 3g-3 adds one small endpoint and the operator
viewer.

## Backend (one new endpoint)

Add a tenant-context audit-log route. The schema-agnostic `AuditQueryService`
(`app/platform_/audit/service.py`) and the `AuditEntryOut` / `AuditLogPage`
schemas (`app/platform_/audit/schemas.py`) are reused unchanged.

- **New** `GET /audit-log` (operator), gated `CurrentTenantUser`, session via
  `get_tenant_session` (resolves the caller's own tenant schema by search_path —
  operators can only ever read their own tenant's `audit_log`), querying
  `TenantAuditLog`. Same filters + pagination as the platform routes:
  `table_name`, `record_id`, `actor_id`, `actor_type`, `operation`,
  `occurred_from`, `occurred_to`, `page` (≥1), `page_size` (1–100, default 25).
  Returns `AuditLogPage` ordered `occurred_at DESC, id DESC`.

The route lives as a second router (`tenant_router`) in
`app/platform_/audit/api.py`, mirroring the billing module precedent
(`platform_router` + `tenant_router` in one `api.py`). It is mounted from
`app/main.py` alongside the existing platform audit router.

- The route runs **inside `get_tenant_session`**, so the subscription gate
  applies (402/403 for past-due-past-grace / suspended), consistent with every
  other operator route. This is intentional.
- No new permission tier — operators gate on `CurrentTenantUser` only (there is
  no fine-grained tenant RBAC; all Phase-3 operator routes gate this way).
- `impersonation_id` is returned (it is part of `AuditEntryOut`) so the trail is
  honest about platform-support actions, but the operator UI does not render a
  dedicated impersonation column (see Frontend).

## Frontend

The SP19 audit viewer components are reused. They are **relocated** from the
platform route group's private `_components/` to the shared
`admin/apps/portal/src/components/audit/` (where `AuditBarConnected` and
`MakerCheckerBannerConnected` already live), so the operator page does not reach
into another route subtree's private folder.

- **Relocate** `AuditTable`, `JsonDiff`, `AuditOperationLabel` →
  `src/components/audit/`. Update the two platform pages
  (`/platform/audit`, `/platform/tenants/[id]/audit`) and the two existing
  component tests to import from the new location. No behavior change.
- **`AuditTable`** gains an optional `tableId?: string` prop (default
  `"platform-audit"`, preserving existing behavior) so the operator table uses
  its own `sacco_table_prefs` bucket (`"tenant-audit"`). It already takes
  `items`, `total`, `showImpersonation` and drives a **server-side paginated**
  `<DataTable>` via `useTableUrlState({ shallow: false })` — URL search params
  drive the RSC refetch (the first true server-side table, from SP19). Filters:
  operation `<Select>`, plus table / record-id / actor-id `<Input>`s. Row
  "Details" opens a `<JsonDiff>` before/after dialog.

- **api-client** `resources.audit` gains
  `listOperator: (query) => GET /audit-log` (the only api-client change).

### Screen

- **`/audit`** (under `app/(tenant-authed)/audit/`) — server component:
  reads `searchParams`, builds the query (page/pageSize + `f_*` filters →
  api keys), fetches `resources.audit.listOperator(query)`, renders
  `<AuditTable items total tableId="tenant-audit" showImpersonation={false} />`.
  Clones the platform `/audit` index page, swapping
  `getPlatformPageContext()` + `requirePlatformPermission` for
  `getTenantPageContext()` (auth-only) and `listPlatform` for `listOperator`.

### Sidebar

The tenant sidebar's `/audit` item is currently wrapped in
`<PermissionGuard permission="audit.read">`. `audit.read` maps to the platform
`admin` role, which tenant operators never have, so the link is hidden from
them. Remove the guard around the **tenant** (`variant === "tenant"`) `/audit`
`SidebarItem` only — matching `/approvals` and every other ungated tenant link.
The **platform** sidebar's `audit.read` guard is unchanged. The backend
(`CurrentTenantUser`) is the real gate; UI gating is UX only (contract D).

## Out of scope (deferred)

- A dedicated impersonation column in the operator view (the `actor_label`
  already carries `"<email> (impersonating)"` per the impersonation contracts;
  the raw `impersonation_id` is platform-ops detail).
- `<AuditBar>` lighting up on tenant operator entity detail pages — the
  `AuditBarConnected` component is platform-context (`getPlatformPageContext`);
  a tenant-context `AuditBarConnected` that calls `listOperator` is a worthwhile
  follow-up but is not required to fill the `/audit` link.
- CSV export of the audit log (a reporting-endpoint concern, like every other
  list; client CSV covers the loaded page only via the DataTable toolbar).
- Cursor pagination (offset pagination like SP19).

## Testing strategy

- **Backend** (`tests/platform_/audit/test_audit_api.py`, real Postgres
  `sacco/sacco@localhost:5433/sacco_test`): the operator `GET /audit-log` lists
  the caller's tenant `audit_log` rows and honors a filter. Override
  `get_tenant_session` with a `tenant_test`-schema session, seed a
  `TenantAuditLog` row + a `tenant_users` actor, call with stub tenant headers
  (`X-Tenant-Slug` + `X-Tenant-Actor-ID`). Mirror the `tests/modules/maker_checker/test_api.py`
  tenant-auth harness.
- **@sacco/portal:** the relocated `AuditTable` / `JsonDiff` tests pass from the
  new path (no behavior change). The operator `/audit` page is thin server
  wiring (no new unit test — covered by the reused `AuditTable` tests).
- Per-package `test` + `typecheck` + `lint` green; backend `ruff` + `mypy`
  clean. Platform audit endpoints + viewer remain green (regression guard for
  the relocation).
