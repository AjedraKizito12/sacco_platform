# Global Search — Increment 2 (Breadth + Palette Polish) Design

**Status:** Approved (brainstorming, 2026-07-12)
**Builds on:** Increment 1 (merged to `main`, `app/core/search/`) — ES pipeline,
reconcile beat, schema-isolated query endpoints, `CommandPalette`.
**Increment-1 spec:** `docs/superpowers/specs/2026-07-12-global-search-design.md`

## Goal

Extend the working ES-backed ⌘K search from two entity types to the full
operator + platform surface, show each result's status, add
navigation-command actions, and close the hard-delete orphan gap — all on the
Increment-1 pipeline (no new infrastructure, no new architecture).

## Key decisions (resolved in brainstorming)

- **No cross-tenant member search.** Platform search stays scoped to
  platform-owned entities; members remain searchable only within their own
  tenant by that tenant's operators. Support reaches a member via the existing
  audited impersonation flow.
- **Terminal-state records stay searchable, with status shown.** Exited members,
  archived tenants, withdrawn/rejected applications, void invoices, cancelled
  subscriptions all remain in the index; each hit carries a `StatusBadge`. Plus a
  periodic **delete-sweep** removes ES docs whose source row genuinely vanished.
- **Nav actions derived from `nav-config`** (DRY), not a separate hand-kept list.
- **Single plan** (~8–10 tasks), not decomposed further.

## New entity types

| Entity | Audience | Index | Detail URL | Title / Subtitle | Status entity |
|--------|----------|-------|-----------|------------------|---------------|
| Loan | operator | `sacco_loans` | `/credit/loans/{id}` | member name / loan number | `loan` |
| Savings account | operator | `sacco_savings_accounts` | `/savings/accounts/{id}` | member name / account number | `savings_account` |
| Loan application | operator | `sacco_loan_applications` | `/credit/applications/{id}` | member name / application ref | `loan_application` |
| Invoice | platform | `sacco_invoices` | `/platform/billing/invoices/{id}` | invoice number / tenant | `invoice` |
| Subscription | platform | `sacco_subscriptions` | `/platform/billing/subscriptions/{id}` | tenant / plan | `subscription` |
| Platform user | platform | `sacco_platform_users` | `/platform/users/{id}` | full name / email | `platform_user` |

(The precise source columns and display fields for each are resolved in the
plan against the real models; entities whose exact title/subtitle need a joined
value — e.g. a loan's member name — either denormalise from the row or fall back
to the record's own identifier.)

## Architecture (all on the Inc-1 pipeline)

### Component 1: Index definitions + document mappers
- `indexes.py`: add the six index names + mappings (same `_TEXT` analyzed +
  keyword pattern; tenant entities include `tenant_schema`; every doc adds
  `status` (keyword) + `status_entity` (keyword)). `ensure_indices` picks them up
  automatically (it iterates `INDEX_MAPPINGS`).
- `documents.py`: add a pure mapper per entity (`loan_document(schema, row)`,
  `savings_account_document(...)`, `loan_application_document(...)`,
  `invoice_document(row)`, `subscription_document(row)`,
  `platform_user_document(row)`), each setting `title`/`subtitle`/`url`/`status`/
  `status_entity` + searchable fields. Retro-fit `status`/`status_entity` onto
  the existing `tenant_document` (status entity `tenant`) and `member_document`
  (status entity `member`).

### Component 2: Reconcile extension + delete-sweep
- `reconcile.py`: extend the tenant pass to also reconcile loans / savings /
  applications per active schema, and the platform pass to also reconcile
  invoices / subscriptions / platform users. Same watermark-per-(index, scope).
  The timestamp column is `updated_at` where present; entities lacking it (verify
  Invoice) fall back to `created_at` — the watermark helper takes the column
  name. Per-pass try/except isolation is already in place.
- **New `sweep_deleted_search_docs` beat** (daily): per (index, scope), page all
  ES doc ids and the current source-row id set, and `delete` ES docs whose id is
  not in the source set. Pure helper `orphan_ids(es_ids, source_ids) -> set`
  (unit-tested). Registered in `celery_app.py` beat_schedule at ~24h.

### Component 3: Query API — `types` filter + status in hits
- `SearchHitOut` gains `status: str` and `status_entity: str`.
- `SearchService.search` maps them from `_source`.
- `/search` and `/platform/search` gain an optional `types: str | None` (CSV of
  entity types); when set, restrict the queried indices to those types (still
  ANDing the tenant filter for operator). Default = all of the audience's
  indices. Unknown/foreign types are ignored (operator can never name a platform
  index, and vice versa — the audience's index allow-list is server-side).

### Component 4: Palette — status badges + nav actions
- `@sacco/ui` `CommandPaletteItem` gains optional `status?: string` +
  `statusEntity?: string`; `CommandPalette` renders `<StatusBadge entity status />`
  beside the subtitle when present. A new item kind for nav actions renders
  without a badge (or with an icon). Keyboard nav unchanged.
- `@sacco/schemas`: `SearchHitOut` gains `status`/`status_entity`.
- Portal `AppShellCommandPalette`: map `entity_type` → StatusBadge entity, pass
  status through; build a **nav-action group** from `nav-config` for the audience
  (flatten the nav items to `{label: "Go to <label>", url: href}`), filter by a
  case-insensitive substring of the query, and merge above/below the search hits
  in a "Navigate" group. Selecting a nav action routes like a hit.

### Component 5: Close-out
- CLAUDE.md Search-contracts update: Increment 2 entity set + the delete-sweep +
  nav actions; note cross-tenant member search remains explicitly out.
- End-to-end verification: reconcile indexes all new types for the demo tenant;
  operator ⌘K finds a loan/savings account with its StatusBadge; platform ⌘K
  finds an invoice; a nav action ("Go to Billing") navigates.

## Contracts respected

- Tenant isolation unchanged and still absolute — every new operator index is
  queried with the mandatory `tenant_schema` term filter; platform indices are
  never queried from the operator path and vice versa (server-side allow-list).
- ES is the index, Postgres the source of truth; reconcile + sweep are the only
  ES writers; no domain events consumed; search code imports no module models
  (raw SQL reads).
- StatusBadge entities reused from `status-maps.ts` (contract S); no hand-picked
  badge variants.

## Out of scope (Increment 3+)

- Cross-tenant member search for platform users (decided out).
- Relevance / synonym / typo-tolerance tuning; per-field weighting beyond the
  existing boosts.
- Event-driven / real-time indexing (reconcile stays the sync mechanism).
- Saved searches, search history, recent items.
- Search analytics.

## Testing strategy

- **Pure units:** a document-mapper test per new entity (shape, url, status,
  status_entity); `orphan_ids` set-diff; the `types` → index allow-list resolver.
- **Reconcile:** watermark helper unchanged; a DB-backed reconcile test for one
  new tenant entity + one platform entity (the Inc-1 review's flagged coverage
  gap — close it here) asserting docs land and the watermark advances; a
  delete-sweep test asserting an orphaned ES doc is removed and a live one kept.
- **API (ES-gated):** query returns the new types with `status` populated;
  `types=` narrows results; operator isolation still holds for a new tenant
  entity (seed two schemas' loans, assert cross-schema empty).
- **Frontend:** `CommandPalette` renders a StatusBadge for an item with status
  and a nav-action item without; `AppShellCommandPalette` shows a "Navigate"
  group filtered by query and merges search hits with status badges; new entity
  groups render.
- Backend ruff/mypy + pnpm lint/typecheck/test clean; ES integration tests skip
  when ES is unreachable.

## Open decisions (resolved)

- Cross-tenant member search → **no**.
- Terminal states → **index all, show status, + delete-sweep**.
- Nav actions → **derived from nav-config**.
- Scope → **single plan**, ~8–10 tasks.
