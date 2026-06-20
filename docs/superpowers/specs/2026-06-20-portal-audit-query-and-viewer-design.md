# Portal — Audit Query Endpoint + Viewer (SP19 / P1.7-F) Design

**Date:** 2026-06-20
**Phase:** 2 (Admin Portal), sub-plan 19 — includes the Phase-1.7-F backend audit-log query endpoint
**Status:** Approved

## Goal

Ship the long-pending **audit-log query endpoint** (the "Phase 1.7-F" dependency
that `<AuditBar>` and the Audit nav group wait on) for **both** the platform
schema and per-tenant schemas, then build the portal **Audit Viewer** (platform
+ per-tenant) and light up the real `<AuditBar>` on every platform detail page.

This is the one place the audit *write* trail (already implemented everywhere
via `AuditableMixin` / `record()`) becomes *readable* to operators.

## Contract posture (backend-first; NOT pure-client)

Like SP17, SP19 includes backend work — here a genuinely new **read-only**
surface (two query endpoints), not just a response enrichment. Per CLAUDE.md
contract B this was surfaced and approved during brainstorming. The backend is
the Phase-1.7-F dependency the portal scaffolding already anticipates
(`resources.audit` stub, `queryKeys.audit.*`, `audit.read` permission,
`<AuditBar>` placeholder). Backend lands in its own commits **first**; the portal
consumes it. Shipped as one PR with backend commits preceding portal commits
(the SP17 pattern).

Already in place (verified):

- **api-client:** `resources.audit` exists but **empty** (stub comment: "Methods
  will be added once `/platform/audit-log` endpoints land"). `queryKeys.audit.{root,
  platform, tenant, detail}` exist.
- **permissions:** `audit.read → admin`.
- **@sacco/ui:** `<AuditBar>` is a placeholder (`entityType`/`entityId` props,
  renders "coming soon"); `<DataTable>` already runs `manualPagination: true` and
  reads `state.totalRows` (built for server-side paging); `RelativeTime`,
  `FormattedDateTime`, `StatusBadge`, `Card`, `Select`.
- **AuditBar consumers:** 6 platform detail pages — entityTypes `subscription`,
  `subscription_plan`, `approval_request`, `invoice`, `platform_user`, `tenant`.
- **Backend:** `_AuditLogBase` (shared columns) → `PlatformAuditLog`
  (`platform.audit_log`) + `TenantAuditLog` (`<tenant>.audit_log`, adds
  `impersonation_id`). Indexes on `(table_name, record_id)` and `occurred_at DESC`.
  `AuditableMixin` writes `table_name = __tablename__` (physical plural names).
  `get_session_for_tenant_schema(tenant_id)` dep exists (used by
  `tenant_users_admin`, NOT subscription-gated).

## Backend facts (authoritative)

`_AuditLogBase` columns: `id, table_name, record_id, operation` (insert|update|
delete), `actor_type` (platform_user|tenant_user|system|api_client), `actor_id`,
`actor_label`, `before_state` (JSONB), `after_state` (JSONB), `occurred_at`,
`request_id`. `TenantAuditLog` adds `impersonation_id`.

Physical `table_name` values for the 6 AuditBar entities:
`subscription→subscriptions`, `subscription_plan→subscription_plans`,
`invoice→invoices`, `platform_user→platform_users`, `tenant→tenants`,
`approval_request→approval_requests`.

## Part 1 — Backend: `app/platform_/audit/` module (separate commits, lands first)

New module `app/platform_/audit/{__init__,api,service,schemas}.py`, mounted from
`app/main.py`. Mirrors the `tenant_users_admin` module layout.

### Endpoints (both gate `CurrentAdmin` = `audit.read`)

| Endpoint | Session dep | Source table |
|----------|-------------|--------------|
| `GET /platform/audit-log` | `get_platform_session` | `platform.audit_log` |
| `GET /platform/tenants/{tenant_id}/audit-log` | `get_session_for_tenant_schema` | `<tenant>.audit_log` |

Both accept the same query params and return the same envelope. The tenant
endpoint additionally surfaces `impersonation_id`. The tenant endpoint is NOT
subscription-gated (the dep guarantees this).

### Query params (shared)

`table_name?: str`, `record_id?: UUID`, `actor_id?: UUID`, `actor_type?: str`,
`operation?: str`, `occurred_from?: datetime`, `occurred_to?: datetime`,
`page: int = 1` (≥1), `page_size: int = 25` (1..100). Results ordered
`occurred_at DESC, id DESC` (stable tiebreak).

### Response envelope (paginated — a first for platform lists)

```
AuditLogPage {
  items: list[AuditEntryOut]
  total: int           # COUNT(*) over the same filter (no pagination)
  page: int
  page_size: int
}
```

`AuditEntryOut` mirrors `_AuditLogBase` + `impersonation_id: UUID | None = None`
(always null from the platform endpoint; populated from the tenant endpoint).
`before_state` / `after_state` are `dict | None`.

### Service

`AuditQueryService(session)` with `async def query(*filters, page, page_size) ->
tuple[list[rows], total]`. Builds a single filtered `select(...)` + a `count()`
over the same `where`. The model class (`PlatformAuditLog` vs `TenantAuditLog`)
is chosen by the caller (the platform handler passes the platform model; the
tenant handler passes the tenant model) — the service takes the model class so
it stays schema-agnostic, like `ApprovalService`.

### Pagination & index note

Offset pagination (`OFFSET (page-1)*page_size LIMIT page_size`). The default
sort uses the `occurred_at DESC` index. A `record_id`-only filter (AuditBar) does
not hit the leading-column `(table_name, record_id)` index unless `table_name` is
also supplied — the AuditBar always supplies both, so it's covered. Deep offsets
on huge logs are a known v1 limitation (cursor pagination is a later optimisation,
out of scope).

### Tests (pytest, real Postgres)

Platform: filter by `record_id`+`table_name`; filter by `operation`; date-range;
pagination (`total` vs page slice); ordering. Tenant: same against a tenant schema
via `get_session_for_tenant_schema`, asserting `impersonation_id` surfaces. Reuse
the `test_platform_api.py` stub-auth (`X-Platform-Actor-ID`) + `test_engine`
fixture conventions.

## Part 2 — Portal schemas & api-client (`@sacco/schemas`, `@sacco/api-client`)

- `@sacco/schemas`: hand-write `AuditEntryOut` + `AuditLogPage` (mirror the
  Pydantic; `before_state`/`after_state` as `Record<string, unknown> | null`;
  `AUDIT_OPERATION_OPTIONS` = insert/update/delete for the filter select).
- `@sacco/api-client`: fill `resources.audit`:
  - `listPlatform(query?) → GET /platform/audit-log`
  - `listTenant(tenantId, query?) → GET /platform/tenants/{tenant_id}/audit-log`
  Both carry the `Promise<never>` wart → cast to `{ data?, error? }`. (Unlike the
  `as never` admin stubs, these are written fresh with the same cast convention.)

## Part 3 — `useTableUrlState` server-side option (`@sacco/ui`, additive)

The audit viewer is the **first true server-side paginated table**. Existing
tables use `useTableUrlState` with nuqs's default `shallow: true` (client-only URL
update; no RSC refetch) + in-memory adaptation. Audit data is unbounded and
server-paginated, so URL changes must trigger an RSC refetch.

**Additive change:** `useTableUrlState({ ..., shallow?: boolean })` — default
`true` (every existing caller unchanged). When `false`, both internal
`useQueryStates` calls pass `{ shallow: false }`, so page/sort/filter changes do a
real Next.js navigation that re-runs the server component. No existing caller
passes `shallow`, so behaviour is identical for them. (Verify nuqs's
`useQueryStates` accepts a per-call `{ shallow }` options arg; if it's
adapter-level only, fall back to passing `shallow` on each parser's options — the
plan resolves this against the installed nuqs version.)

## Part 4 — Portal Audit Viewer screens

### Server-side table data flow (new pattern)

The page is a **server component** that reads `searchParams` (`page`, `pageSize`,
`sort`, `dir`, `f_table_name`, `f_actor_id`, `f_operation`, `f_record_id`,
`f_occurred_from`, `f_occurred_to`), builds the query, fetches the matching server
page, and passes `items` + `total` to a client `<AuditTable>`. `<AuditTable>` calls
`useTableUrlState({ shallow: false, ... })` purely to render DataTable's UI state
and update the URL; the **data** arrives via props from the server. A URL change →
server re-render → fresh fetch → new `items`/`total` down to the table.

### `/platform/audit` (list)

- Columns: **When** (`<FormattedDateTime>`), **Table** (`table_name`), **Record**
  (`record_id`, monospace), **Operation** (plain coloured text label — insert =
  positive tone, update = neutral, delete = danger; not a `StatusBadge`, since an
  audit operation is not a domain status and adding an entity would be scope
  creep), **Actor** (`actor_label ?? actor_id ?? actor_type`), and a **Details**
  affordance per row that opens the before/after diff.
- Filters (DataTable `filterSlot`): table_name (text), operation (Select:
  insert/update/delete), actor_id (text), record_id (text), occurred_from/to (date).
- Server-side pagination via the Part-3 mechanism. Gate `audit.read`.

### Entry detail — inline drawer, no separate route (decided)

There is **no `GET /audit-log/{id}`** endpoint and none is added. An audit row
already carries its own `before_state` / `after_state`, so the **before/after
diff renders inline**: clicking a row's "Details" opens a drawer/expander showing
`<JsonDiff before={row.before_state} after={row.after_state} />` for that row. No
`/audit/[id]` route, no id-lookup endpoint, no brittle client re-filter.
`queryKeys.audit.detail` stays unused for now.

### `<JsonDiff before after />` (portal component)

Two-column before→after JSON view: union of keys, each row shows old vs new with
changed keys highlighted; unchanged keys dimmed; handles null `before` (insert) and
null `after` (delete). Reuses the SP17 `PayloadView` raw-JSON styling
(`--surface-sunken`).

### `/platform/tenants/[id]/audit` (tenant viewer)

Same `<AuditTable>` fed by `listTenant(tenantId, query)`, plus an **Impersonation**
column (`impersonation_id`, shown when present). Linked from the tenant detail page
(`TenantDetail`) as an "Audit log" action. Reads the tenant id from the route.

## Part 5 — `<AuditBar>` evolution + wiring

### `@sacco/ui` `<AuditBar>` (presentational, back-compat)

Add optional props: `entries?: AuditBarEntry[]`, `viewAllHref?: string`,
`isLoading?: boolean`. `AuditBarEntry = { id: string; operation: string;
actorLabel: string | null; occurredAt: string }` (a minimal presentational shape —
`@sacco/ui` cannot import `@sacco/schemas`).

- `entries === undefined` → current "coming soon" placeholder (existing
  tests/Storybook unchanged).
- `entries` provided → list each (operation · `actorLabel` · `<RelativeTime
  value={occurredAt}/>`); empty array → "No recent activity"; `viewAllHref` →
  enabled "View Full History" link (replaces the disabled button).

### Portal `<AuditBarConnected entityType entityId />`

Server component. Maps `entityType → table_name` via a small portal const
(`AUDIT_TABLE_BY_ENTITY`), fetches `listPlatform({ table_name, record_id:
entityId, page_size: 5 })`, maps `AuditEntryOut[] → AuditBarEntry[]`, and renders
`<AuditBar entries viewAllHref={/platform/audit?f_record_id=<id>&f_table_name=<t>} />`.
On fetch error → render `<AuditBar entityType entityId />` (placeholder fallback).

The 6 platform detail pages swap `<AuditBar entityType=… entityId=… />` →
`<AuditBarConnected entityType=… entityId=… />` (call sites keep the semantic
entityType; only the import + component name change).

## Permission mapping (authoritative)

| Action | Backend gate | Portal gate |
|--------|--------------|-------------|
| Platform audit list / AuditBar | `CurrentAdmin` | `audit.read` |
| Tenant audit list | `CurrentAdmin` | `audit.read` |

## Out of scope (deferred)

- **CSV / bulk export** of audit results — reporting-endpoint territory.
- **Audit retention / archival / immutability tooling** — ops concern, separate.
- **Cursor pagination** — offset is the v1 contract; deep-offset perf is a known
  limitation.
- **A dedicated `GET /audit-log/{id}`** — the inline expand/diff avoids it.
- **Real-time / streaming audit** — out of scope.
- **e2e + next-intl** — portal-wide deferrals (raw English), matching SP12–18.

## Testing strategy

- **Backend:** pytest (real Postgres) — platform + tenant query filters, pagination
  envelope, ordering, `impersonation_id` surfacing.
- **Portal:** Vitest + Testing Library — `JsonDiff` (insert/update/delete cases),
  `<AuditBar>` (placeholder when no entries, list when entries, viewAllHref),
  `AuditTable` (row render, links, filter slots — `useTableUrlState` mocked with
  `shallow:false` honoured by the mock), `useTableUrlState` shallow-option unit
  test. Per-package `test` + `typecheck` + `lint` green; all portal changes under
  `admin/`, all backend under `app/` + `tests/`.
