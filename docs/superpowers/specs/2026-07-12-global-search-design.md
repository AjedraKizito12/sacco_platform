# Global Search & Command Palette (Design)

**Status:** Approved (brainstorming, 2026-07-12)
**Register:** cross-cutting backend (search indexing + query API) + a portal command-palette surface.

## Goal

Give platform and operator (SACCO admin) portal users a working ⌘K command
palette that searches the records they can see and jumps straight to a record's
detail page — replacing the disabled "Search coming soon" stub (PR #72). Members
keep no search box (as today).

Backend is **Elasticsearch** (the provisioned-but-unused dependency, now put to
work). Sync is a **reconcile beat** (no new domain events). The feature is
**decomposed into two increments**; this spec covers both, the accompanying plan
builds Increment 1.

## Scope decomposition

- **Increment 1 — ES foundation + thin end-to-end slice (this plan).** The whole
  pipeline working for the two primary entities: platform → **tenants**,
  operator → **members**. ES client + per-type indices + a watermark reconcile
  beat + permission-scoped query endpoints + the command palette wired into the
  header. Proves the risky ES path end to end.
- **Increment 2 — breadth + polish (later).** Add loans, savings accounts, loan
  applications, invoices, subscriptions, platform users; palette quick-nav
  actions ("Go to Billing"); relevance/ranking tuning; hard-delete/tombstone
  handling; optional cross-tenant member search for platform (a privacy call
  deferred here).

## Key decisions (resolved in brainstorming)

- **Backend:** Elasticsearch (not Postgres). One index per entity type; documents
  tagged with `tenant_schema`; strict tenant filter on operator queries.
- **Sync:** a Celery reconcile beat using `updated_at` watermarks + initial
  backfill. No new CRUD domain events (existing events are milestone-only, and
  adding CRUD events across every module is out of scope). Freshness ~1 minute.
- **UX:** a ⌘K command palette (Dialog-based; no new dependency), server-driven
  results, keyboard nav, Enter → navigate. Not a results page.

## Architecture (Increment 1)

```
  Postgres (platform.tenants, <schema>.members)
        │  reconcile beat (~45s): rows WHERE updated_at > watermark
        ▼
  SearchIndexer ──bulk──▶ Elasticsearch  (sacco_tenants, sacco_members)
        │                        ▲
        │ watermark              │ query (multi_match + tenant_schema filter)
        ▼                        │
  platform.search_index_state    │
                          ┌──────┴───────────────┐
   GET /platform/search ──▶ SearchService.query  │  (CurrentSupport)
   GET /search ───────────▶ (tenant_schema filter)│  (CurrentTenantUser + gate)
                          └──────┬───────────────┘
                                 │ SearchHitOut[] {type,id,title,subtitle,url}
                          ┌──────▼───────────────┐
   ⌘K → AppShellCommandPalette (debounced TanStack query) → CommandPalette (@ui)
                          → Enter → router.push(hit.url)
```

All backend search code lives in `app/core/search/` (cross-cutting; imports
nothing from `app/modules`/`app/platform_` except read-only row selects for
indexing).

### Component 1: ES client + index definitions

- `app/core/search/client.py` — a shared `get_search_client()` returning a
  configured `AsyncElasticsearch` from `settings.elasticsearch_url` (replacing
  the ad-hoc client in the health check's usage over time; health check untouched
  in Inc 1).
- `app/core/search/indexes.py` — index names (`sacco_tenants`, `sacco_members`)
  and their mappings. Text fields analyzed (standard analyzer) with `keyword`
  sub-fields; a `tenant_schema` keyword on tenant-owned docs; `entity_type`,
  `record_id`, and display fields (`title`, `subtitle`) stored for rendering.
  `ensure_indices()` creates missing indices idempotently (called on beat start).
- Doc id: `<schema>:<uuid>` for tenant entities, `<uuid>` for platform entities
  (collision-free across tenants).

### Component 2: Document mappers + SearchService

- `app/core/search/documents.py` — pure row→document mappers:
  `tenant_document(row) -> dict`, `member_document(schema, row) -> dict`. Set
  `title`/`subtitle`/`url` for the palette (e.g. member → title=full_name,
  subtitle=member_number, url=`/members/{id}`; tenant → title=name,
  subtitle=slug, url=`/platform/tenants/{id}`). Pure functions (unit-tested
  without ES).
- `app/core/search/service.py` — `SearchService`:
  - `bulk_index(index, docs)` / `ensure_indices()` (indexing side).
  - `query(indices, q, *, tenant_schema=None, limit=20) -> list[SearchHit]` —
    builds a `multi_match` over the analyzed fields across the given indices;
    when `tenant_schema` is set, ANDs a `term` filter `tenant_schema=<schema>`
    (the tenant-isolation guarantee). Returns typed hits.
  - Query DSL construction is unit-tested as a pure builder (no ES); one
    integration smoke exercises a real round-trip against the dev ES.

### Component 3: Reconcile beat + watermark state

- `alembic/platform/versions/013_search_index_state.py` — `platform.search_index_state`
  `(index_name text, scope text, last_watermark timestamptz, last_run_at
  timestamptz, PRIMARY KEY(index_name, scope))`. `scope` = tenant `schema_name`
  for tenant entities, `'platform'` for platform entities.
- `app/core/search/reconcile.py` — `reconcile_search_indexes` Celery beat
  (~45s): `ensure_indices()`; for `sacco_tenants` (scope `platform`) select
  `platform.tenants WHERE updated_at > watermark`; for `sacco_members` iterate
  active tenant schemas (same helper the notifications beat uses) and select
  `<schema>.members WHERE updated_at > watermark` per scope; bulk-index; advance
  each watermark to the max `updated_at` seen. First run (watermark = epoch)
  backfills. Registered in `celery_app.py` `include` + `beat_schedule`.

### Component 4: Query API (permission-scoped)

- `app/core/search/api.py` — two routers mounted in `app/main.py`:
  - `platform_search_router`: `GET /platform/search?q=&limit=` — gated
    `CurrentSupport` (any authenticated platform user). Queries `sacco_tenants`.
    Returns `SearchResultsOut`.
  - `tenant_search_router`: `GET /search?q=&limit=` — gated `CurrentTenantUser`
    + the subscription gate (`get_tenant_session`). Resolves the caller's
    `tenant_schema` and passes it to `query(...)` as the mandatory filter.
    Queries `sacco_members`. NEVER cross-tenant.
- Schemas: `SearchHitOut {entity_type, id, title, subtitle, url}`,
  `SearchResultsOut {hits: list[SearchHitOut], took_ms: int}`. Empty `q`
  (< 1 non-space char) → empty hits, no ES call.
- Permission-scoping tests assert an operator's query only ever hits their own
  schema's docs (seed two schemas, confirm isolation).

### Component 5: Frontend — palette + client

- `@sacco/schemas` — `SearchHitOut` / `SearchResultsOut` wire types.
- `@sacco/api-client` — `search` resource: `platformSearch(q)`, `tenantSearch(q)`;
  query keys `search.platform(q)` / `search.tenant(q)`.
- `@sacco/ui` — `CommandPalette` (presentational, Dialog-based): props
  `open`, `onOpenChange`, `query`, `onQueryChange`, `groups: {label, items:
  SearchHitItem[]}[]`, `loading`, `onSelect(item)`. A search input, grouped
  keyboard-navigable list (roving focus, ↑/↓/Enter/Esc), empty + loading states.
  No new dependency (built on the existing `Dialog`). Server-driven results, so
  no client-side filtering engine needed.
- Portal `AppShellCommandPalette` (client): owns open state + a global ⌘K / Ctrl-K
  keydown listener; debounces the query (~200ms) and fetches the audience
  endpoint via TanStack Query; maps hits to groups; `onSelect` → `router.push(
  hit.url)` + close. Wired into `AppShellHeader`: the `CommandPaletteTrigger`'s
  `onActivate` opens it (for platform + operator; member stays null). This
  supersedes the PR #72 disabled state for those two audiences.

## Contracts respected / added

- Multi-tenancy: operator search ALWAYS ANDs `tenant_schema = <caller>`; the
  endpoint derives the schema server-side (never from the client). Cross-tenant
  search is impossible in the operator path.
- Outbox rule (9): unaffected — indexing is a read-only reconciler, not an event
  publisher; it does not touch RabbitMQ.
- New **Search contracts** (added to CLAUDE.md): all search code in
  `app/core/search/`; ES is the index, Postgres is the source of truth; the
  reconcile beat is the only writer of ES documents; operator queries are
  schema-filtered; `/search` and `/platform/search` are the only query surfaces.
- Scope exception (like Phase 4/5): edits `docker-compose.yml` only if ES needs
  config changes (it doesn't in Inc 1 — ES already runs), adds
  `app/core/search/`, a platform migration, and the palette portal code.

## Out of scope (Increment 1)

- All Increment-2 entity types (loans, savings, applications, invoices,
  subscriptions, platform users).
- Palette quick-nav actions ("Go to Billing").
- Relevance/ranking tuning, synonyms, fuzzy typo-tolerance beyond ES defaults.
- Hard-delete/tombstone handling (rare here; entities aren't hard-deleted in Inc
  1's set — members are never hard-deleted, tenants are archived not deleted).
- Cross-tenant member search for platform users (privacy decision deferred).
- Member-audience search (stays hidden).

## Testing strategy (Increment 1)

- **Pure units (no ES):** document mappers (row → doc shape, url/title/subtitle);
  the query-DSL builder (multi_match + mandatory tenant filter when schema set);
  watermark advancement logic.
- **Integration (dev ES):** one round-trip — index two members in two schemas +
  two tenants, query, assert (a) operator query returns only its schema's member,
  (b) platform query returns the tenant, (c) empty q short-circuits. Runs against
  the ES container (the same way integration tests use real Postgres). Offline
  `alembic upgrade --sql` is broken repo-wide; smoke migration 013 against a
  scratch DB.
- **API:** endpoint permission gating (platform=CurrentSupport, tenant=
  CurrentTenantUser+gate), schema-isolation, empty-query behavior.
- **Frontend:** `CommandPalette` vitest (renders groups, keyboard nav selects,
  Esc closes, empty/loading states); `AppShellCommandPalette` (⌘K opens,
  debounced query fires, select navigates); header wiring (trigger opens palette
  for platform/operator).
- pnpm + ruff/mypy clean.

## Open decisions (resolved)

- Backend → **Elasticsearch pipeline**.
- Sync → **reconcile beat** (watermark + backfill; no new events).
- UX → **command palette** (Dialog-based, no new dep).
- Index strategy → **one index per entity type**, tenant-tagged docs, mandatory
  tenant filter (not per-tenant indices).
- Increment 1 slice → **tenants (platform) + members (operator)** end to end.
