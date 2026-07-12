# Global Search — Increment 2 (Breadth + Palette Polish) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the merged ES-backed ⌘K search from tenants+members to the full surface — loans, savings accounts, loan applications (operator) and invoices, subscriptions, platform users (platform) — with a StatusBadge on every hit, a `types` query filter, nav-action commands in the palette, and a delete-sweep that removes orphaned ES docs. All on the Increment-1 pipeline.

**Architecture:** Pure per-entity document mappers feed the existing reconcile beat (two more scopes' worth of entities) and the same one-index-per-type ES model, each doc now carrying `status`/`status_entity`. A new daily delete-sweep beat diffs ES ids against source ids. The query endpoints gain an optional `types=` filter over a server-side per-audience allow-list; operator isolation (mandatory `tenant_schema` filter) is unchanged. The palette renders StatusBadges and a nav-action group derived from `nav-config`.

**Tech Stack:** Python 3.11, Elasticsearch (AsyncElasticsearch), SQLAlchemy async, Celery beat, Next.js 15, `@sacco/ui`/`api-client`/`schemas`, vitest.

**Spec:** `docs/superpowers/specs/2026-07-12-global-search-increment-2-design.md`
**Inc-1 context:** `app/core/search/` (client, indexes, documents, service, reconcile, api, schemas), `admin/packages/ui/src/components/CommandPalette/`, `admin/apps/portal/src/components/AppShellCommandPalette.tsx`.

Branch: `feat/search-inc2` (from `main`).

## Global Constraints

- **Tenant isolation is absolute and unchanged:** every new operator index is queried ONLY through the tenant path with the mandatory `tenant_schema` term filter (already in `SearchService.build_query`). Platform indices are NEVER queried from the operator path and vice versa — enforced by a server-side per-audience index allow-list. The client-supplied `types=` can only narrow within the audience's own allow-list; a foreign type is ignored, never honored.
- **ES is the index; Postgres the source of truth.** The reconcile beat + the new delete-sweep beat are the ONLY ES writers. No domain events consumed. Search code imports NO module models — read rows via raw SQL under `SET LOCAL search_path` (tenant) or `platform.` qualification.
- **No new migration** (no new tables; the `search_index_state` table already covers all (index, scope) pairs).
- **StatusBadge entities** come from `admin/packages/ui/src/components/StatusBadge/status-maps.ts` (contract S) — reuse `loan`, `savings_account`, `loan_application`, `invoice`, `subscription`, `platform_user`, `tenant`, `member`; never hand-pick a variant.
- **Nav actions derive from `nav-config`** (flatten groups→items→hrefs), not a separate list.
- ruff + mypy (strict) clean; pnpm lint/typecheck/test clean; ES integration tests skip when ES is unreachable (`get_search_client().ping()`), following the Inc-1 `tests/core/search/test_api.py` gate pattern.
- Scope exception continues (search touches `app/core/search/`, `app/workers/celery_app.py`, and the palette portal code).

## File Structure

```
app/core/search/indexes.py         (modify: 6 new index mappings; +status/status_entity on all)
app/core/search/documents.py       (modify: 6 new mappers; +status/status_entity on tenant/member)
app/core/search/service.py         (modify: SearchHit +status/status_entity; types→indices resolver)
app/core/search/reconcile.py       (modify: reconcile the 6 new entities; watermark col param)
app/core/search/sweep.py           (create: orphan_ids + sweep_deleted_search_docs beat)
app/core/search/api.py             (modify: types= param; per-audience allow-list)
app/core/search/schemas.py         (modify: SearchHitOut +status/status_entity)
app/core/search/registry.py        (create: single source of the entity→index/scope/columns table)
app/workers/celery_app.py          (modify: include sweep + beat_schedule)
tests/core/search/test_documents.py         (modify: new-entity mapper tests)
tests/core/search/test_sweep.py              (create)
tests/core/search/test_reconcile_db.py       (create: DB-backed reconcile — closes Inc-1 gap)
tests/core/search/test_api.py                (modify: types filter + new-entity isolation)

admin/packages/schemas/src/search.ts         (modify: +status/status_entity)
admin/packages/api-client/src/resources/search.ts (modify: optional types arg)
admin/packages/ui/src/components/CommandPalette/CommandPalette.tsx (modify: StatusBadge + nav-action kind)
admin/packages/ui/src/components/CommandPalette/CommandPalette.test.tsx (modify)
admin/apps/portal/src/components/AppShellCommandPalette.tsx (modify: status map + nav-action group)
admin/apps/portal/src/components/search/nav-actions.ts (create: flatten nav-config)
admin/apps/portal/src/__tests__/search/*                (modify/create)

CLAUDE.md   (modify: Increment-2 search contracts)
```

---

### Task 1: Entity registry (single source of the mapping table)

**Files:**
- Create: `app/core/search/registry.py`

**Interfaces:**
- Produces: `SEARCH_ENTITIES: list[SearchEntity]` where `SearchEntity` is a frozen dataclass `(entity_type, index, scope_kind ("platform"|"tenant"), table, timestamp_col, status_entity)`; helpers `platform_indices() -> list[str]`, `tenant_indices() -> list[str]`, `resolve_indices(audience, types) -> list[str]` (audience `"platform"|"tenant"`; `types` optional CSV → intersect with the audience's allow-list; empty/None → all of the audience's indices).

- [ ] **Step 1: Failing test for the resolver**

`tests/core/search/test_registry.py`:
```python
from app.core.search.registry import platform_indices, resolve_indices, tenant_indices


def test_tenant_default_is_all_tenant_indices():
    assert set(resolve_indices("tenant", None)) == set(tenant_indices())


def test_types_narrows_within_audience():
    got = resolve_indices("tenant", "member,loan")
    assert set(got) == {"sacco_members", "sacco_loans"}


def test_foreign_type_is_ignored_not_honored():
    # a tenant caller naming a platform type gets none of it
    got = resolve_indices("tenant", "invoice,member")
    assert got == ["sacco_members"]


def test_platform_default_excludes_tenant_indices():
    assert "sacco_members" not in platform_indices()
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/pytest tests/core/search/test_registry.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `registry.py`**

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchEntity:
    entity_type: str
    index: str
    scope_kind: str  # "platform" | "tenant"
    table: str       # source table (unqualified for tenant, platform.-qualified for platform)
    timestamp_col: str
    status_entity: str


SEARCH_ENTITIES: list[SearchEntity] = [
    SearchEntity("tenant", "sacco_tenants", "platform", "platform.tenants", "updated_at", "tenant"),
    SearchEntity("platform_user", "sacco_platform_users", "platform", "platform.platform_users", "updated_at", "platform_user"),
    SearchEntity("invoice", "sacco_invoices", "platform", "platform.invoices", "updated_at", "invoice"),
    SearchEntity("subscription", "sacco_subscriptions", "platform", "platform.subscriptions", "updated_at", "subscription"),
    SearchEntity("member", "sacco_members", "tenant", "members", "updated_at", "member"),
    SearchEntity("loan", "sacco_loans", "tenant", "loans", "updated_at", "loan"),
    SearchEntity("savings_account", "sacco_savings_accounts", "tenant", "savings_accounts", "updated_at", "savings_account"),
    SearchEntity("loan_application", "sacco_loan_applications", "tenant", "loan_applications", "updated_at", "loan_application"),
]

_BY_TYPE = {e.entity_type: e for e in SEARCH_ENTITIES}


def platform_indices() -> list[str]:
    return [e.index for e in SEARCH_ENTITIES if e.scope_kind == "platform"]


def tenant_indices() -> list[str]:
    return [e.index for e in SEARCH_ENTITIES if e.scope_kind == "tenant"]


def resolve_indices(audience: str, types: str | None) -> list[str]:
    allowed = platform_indices() if audience == "platform" else tenant_indices()
    if not types:
        return allowed
    wanted = {t.strip() for t in types.split(",") if t.strip()}
    return [
        _BY_TYPE[t].index
        for t in wanted
        if t in _BY_TYPE and _BY_TYPE[t].index in allowed
    ]
```
(Verify the real table names against models before finalizing: `savings_accounts`, `loan_applications`, `loans`, `platform.invoices`, `platform.subscriptions`, `platform.platform_users`. Fix any that differ.)

- [ ] **Step 4: Run + mypy + ruff**

Run: `venv/bin/pytest tests/core/search/test_registry.py -v && venv/bin/mypy app/core/search/registry.py && venv/bin/ruff check app/core/search/`
Expected: PASS + clean.

- [ ] **Step 5: Commit**

```bash
git add app/core/search/registry.py tests/core/search/test_registry.py
git commit -m "feat(search): entity registry + per-audience index allow-list resolver"
```

---

### Task 2: Index mappings + document mappers (+status on all)

**Files:**
- Modify: `app/core/search/indexes.py`, `app/core/search/documents.py`
- Test: `tests/core/search/test_documents.py`

**Interfaces:**
- Produces: `INDEX_MAPPINGS` entries for all 8 indices (each mapping adds `status` + `status_entity` keyword fields; tenant indices include `tenant_schema`); document mappers for the 6 new entities plus `status`/`status_entity` retro-fitted onto `tenant_document` and `member_document`.

- [ ] **Step 1: Failing mapper tests**

Add to `tests/core/search/test_documents.py` a test per new entity (SimpleNamespace row → assert `entity_type`, `status`, `status_entity`, `url`, `title`, `subtitle`), and assert the existing `tenant_document`/`member_document` now include `status`/`status_entity`. Example:
```python
def test_loan_document_shape():
    from app.core.search.documents import loan_document
    import uuid
    lid = uuid.uuid4()
    row = SimpleNamespace(id=lid, loan_number="L-0001", member_name="Grace N", status="disbursed")
    doc = loan_document("tenant_demo_sacco", row)
    assert doc["entity_type"] == "loan"
    assert doc["tenant_schema"] == "tenant_demo_sacco"
    assert doc["status"] == "disbursed"
    assert doc["status_entity"] == "loan"
    assert doc["url"] == f"/credit/loans/{lid}"
```
(Resolve each entity's real display fields against the models: loans have `loan_number`, a member link — denormalise `member_name` in the reconcile SELECT via a join, or fall back to `loan_number` as title; savings accounts `account_number`; applications a ref; invoices `invoice_number`; subscriptions plan/tenant; platform users `full_name`/`email`. Where a joined display value is awkward, title = the record's own identifier, subtitle = status or a secondary id.)

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/pytest tests/core/search/test_documents.py -v`
Expected: FAIL for the new entities.

- [ ] **Step 3: Implement mappers + mappings**

Add the six mappers to `documents.py` following the Inc-1 shape (each: `entity_type`, `record_id`, `tenant_schema` for tenant entities, `title`, `subtitle`, `url`, `status`, `status_entity`, searchable fields). Add `status`/`status_entity` to `tenant_document` and `member_document`. In `indexes.py` add the six index mapping bodies (mirror the members mapping; include `status`/`status_entity` keyword on ALL indices, `tenant_schema` on tenant ones), keyed by the index name so `ensure_indices` picks them up.

- [ ] **Step 4: Run + mypy + ruff**

Run: `venv/bin/pytest tests/core/search/test_documents.py -v && venv/bin/mypy app/core/search/ && venv/bin/ruff check app/core/search/`
Expected: PASS + clean.

- [ ] **Step 5: Commit**

```bash
git add app/core/search/indexes.py app/core/search/documents.py tests/core/search/test_documents.py
git commit -m "feat(search): index mappings + document mappers for 6 new entity types"
```

---

### Task 3: Reconcile the new entities (registry-driven)

**Files:**
- Modify: `app/core/search/reconcile.py`
- Test: `tests/core/search/test_reconcile_db.py` (DB-backed — closes the Inc-1 coverage gap)

**Interfaces:**
- Consumes: `SEARCH_ENTITIES`, mappers, `SearchService`.
- Produces: the beat now reconciles every registry entity. Refactor the two hand-written passes into a registry-driven loop: platform-scope entities reconciled once (scope `platform`); tenant-scope entities reconciled per active schema. A `_reconcile_entity(engine, svc, entity, scope)` helper reads `SELECT ... FROM {table} WHERE {timestamp_col} >= :wm ORDER BY {timestamp_col}` (tenant entities under `SET LOCAL search_path`), maps via the entity's mapper (dispatch by `entity_type`), bulk-indexes, advances the watermark. Keep the `>=` boundary and per-scope try/except from Inc-1.

- [ ] **Step 1: Failing DB-backed reconcile test**

`tests/core/search/test_reconcile_db.py` (ES-gated + real test DB): seed a row in a tenant schema's `loans` (or reuse an existing seeded demo row) and a `platform.invoices` row, run the relevant `_reconcile_entity`, assert (a) the ES doc exists with the right `status`/`url`, (b) the `search_index_state` watermark advanced. Skip if ES unreachable. This is the DB round-trip the Inc-1 review flagged as missing.

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/pytest tests/core/search/test_reconcile_db.py -v`
Expected: FAIL (new entities not reconciled).

- [ ] **Step 3: Implement the registry-driven reconcile**

Refactor `reconcile.py`: a mapper dispatch `_DOC = {"tenant": tenant_document, "member": member_document, "loan": ...}` keyed by `entity_type` (tenant entities take `(schema, row)`, platform entities take `(row)`); `_reconcile_entity` builds the SELECT from the entity's `table`/`timestamp_col`. `_run` iterates `SEARCH_ENTITIES`: platform ones once; group tenant ones and iterate per active schema (open one session per schema, reconcile all tenant entities under that schema's search_path). Preserve `ensure_indices`, the `>=` boundary, per-scope try/except, and the watermark upsert.

- [ ] **Step 4: Run + live smoke + mypy/ruff**

Run: `venv/bin/pytest tests/core/search/test_reconcile_db.py tests/core/search/test_reconcile.py -v`, then a live smoke (worker DB env): run `reconcile_search_indexes()` and `curl` the new indices' `_count` (non-zero where demo data exists). `venv/bin/mypy app/core/search/ && venv/bin/ruff check app/core/search/`.
Expected: PASS + clean + non-zero counts for seeded types.

- [ ] **Step 5: Commit**

```bash
git add app/core/search/reconcile.py tests/core/search/test_reconcile_db.py
git commit -m "feat(search): registry-driven reconcile for all entity types + DB-backed test"
```

---

### Task 4: Delete-sweep beat

**Files:**
- Create: `app/core/search/sweep.py`
- Modify: `app/workers/celery_app.py`
- Test: `tests/core/search/test_sweep.py`

**Interfaces:**
- Produces: pure `orphan_ids(es_ids: set[str], source_ids: set[str]) -> set[str]`; `sweep_deleted_search_docs` Celery beat (~daily) that, per registry entity + scope, collects ES doc ids (scan) and current source ids (`SELECT id ...`), deletes `orphan_ids(...)` from ES. Registered in `celery_app.py` include + beat_schedule at `24 * 3600.0`.

- [ ] **Step 1: Failing sweep test**

`tests/core/search/test_sweep.py`:
```python
from app.core.search.sweep import orphan_ids


def test_orphan_ids_returns_es_only():
    es = {"a", "b", "c"}
    src = {"b", "c"}
    assert orphan_ids(es, src) == {"a"}


def test_no_orphans_when_source_superset():
    assert orphan_ids({"a"}, {"a", "b"}) == set()
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/pytest tests/core/search/test_sweep.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `sweep.py`**

`orphan_ids` = `es_ids - source_ids`. The beat mirrors reconcile's engine/session/active-schema handling; for each entity+scope, scan ES ids for that index filtered to the scope (tenant entities: `term tenant_schema=<scope>`), build the source id set as `doc_id(scope_or_none, id)` for current rows, delete the difference via ES bulk delete. Guard per scope with try/except. Register the task.

- [ ] **Step 4: Run + mypy/ruff + a live sweep smoke**

Run: `venv/bin/pytest tests/core/search/test_sweep.py -v && venv/bin/mypy app/core/search/sweep.py && venv/bin/ruff check app/core/search/`. Live smoke: index a fake doc id with no source row, run the sweep, confirm it's gone (ES-gated).
Expected: PASS + clean.

- [ ] **Step 5: Commit**

```bash
git add app/core/search/sweep.py app/workers/celery_app.py tests/core/search/test_sweep.py
git commit -m "feat(search): daily delete-sweep for orphaned ES docs"
```

---

### Task 5: API — `types` filter + status in hits

**Files:**
- Modify: `app/core/search/service.py`, `app/core/search/schemas.py`, `app/core/search/api.py`
- Test: `tests/core/search/test_api.py`

**Interfaces:**
- `SearchHit` + `SearchHitOut` gain `status: str`, `status_entity: str` (from `_source`, default `""`). `SearchService.search` maps them. Endpoints gain `types: str | None = Query(None)`; both call `resolve_indices(audience, types)` (Task 1) to pick indices; operator still passes `tenant_schema`.

- [ ] **Step 1: Failing API tests (ES-gated)**

Extend `tests/core/search/test_api.py`: seed a loan doc in `tenant_alpha` + an invoice doc; assert (a) an operator query returns the loan with `status` populated; (b) `types=member` on the operator query excludes the loan; (c) operator isolation holds for loans (alpha loan present, beta loan absent); (d) a platform query with `types=invoice` returns only invoices.

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/pytest tests/core/search/test_api.py -v`
Expected: FAIL (status/types not wired).

- [ ] **Step 3: Implement**

Add `status`/`status_entity` to `SearchHit` (service) + `SearchHitOut` (schemas) + the `_source` mapping. Add `types` param to both endpoints; replace the hardcoded `[TENANTS_INDEX]`/`[MEMBERS_INDEX]` with `resolve_indices("platform"|"tenant", types)`. Keep `_caller_schema` + the mandatory tenant filter for the operator path.

- [ ] **Step 4: Run + mypy/ruff + full search suite**

Run: `venv/bin/pytest tests/core/search/ -q && venv/bin/mypy app/core/search/ && venv/bin/ruff check app/core/search/`
Expected: green + clean.

- [ ] **Step 5: Commit**

```bash
git add app/core/search/service.py app/core/search/schemas.py app/core/search/api.py tests/core/search/test_api.py
git commit -m "feat(search): types= filter + status on hits (registry-scoped indices)"
```

---

### Task 6: schemas + api-client (status + types)

**Files:**
- Modify: `admin/packages/schemas/src/search.ts`, `admin/packages/api-client/src/resources/search.ts`

**Interfaces:**
- `SearchHitOut` gains `status: string`, `status_entity: string`. `search` resource: `platformSearch(q, types?)`, `tenantSearch(q, types?)` (pass `types` in the query when set).

- [ ] **Step 1: Implement + typecheck**

Add the two fields to `SearchHitOut`. Update the resource methods to accept an optional `types?: string` and include it in `params.query` when present. (No new query-key test needed; keys are unchanged — the debounced key is still `(q)`. If `types` becomes user-selectable later, add it to the key then.)

- [ ] **Step 2: Gates**

Run: `pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/api-client typecheck && pnpm --filter @sacco/api-client lint`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add admin/packages/schemas/src/search.ts admin/packages/api-client/src/resources/search.ts
git commit -m "feat(search): status fields + optional types arg on the client"
```

---

### Task 7: `@sacco/ui` CommandPalette — StatusBadge + nav-action kind

**Files:**
- Modify: `admin/packages/ui/src/components/CommandPalette/CommandPalette.tsx`, `CommandPalette.test.tsx`

**Interfaces:**
- `CommandPaletteItem` gains optional `status?: string`, `statusEntity?: string`. When both are set, the row renders `<StatusBadge entity={statusEntity} status={status} />` beside the subtitle. Nav-action items (no status, group "Navigate") render without a badge. Keyboard nav + selection unchanged.

- [ ] **Step 1: Failing test additions**

Add to `CommandPalette.test.tsx`: an item with `status`/`statusEntity` renders a badge (assert the mapped label text, e.g. "Disbursed" for `loan`/`disbursed`); a nav-action item (group "Navigate", no status) renders its title and selects on Enter. Import `StatusBadge` is internal to the component; assert via visible label text.

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm --filter @sacco/ui test -- CommandPalette`
Expected: FAIL.

- [ ] **Step 3: Implement**

Extend `CommandPaletteItem`; in the row, when `item.status && item.statusEntity`, render `<StatusBadge entity={item.statusEntity as never} status={item.status} />` (import from `../StatusBadge`) after the subtitle. Nav-action items just show the title. Keep `data-active` + keyboard nav.

- [ ] **Step 4: Tests + lint + typecheck**

Run: `pnpm --filter @sacco/ui test -- CommandPalette && pnpm --filter @sacco/ui lint && pnpm --filter @sacco/ui typecheck`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add admin/packages/ui/src/components/CommandPalette
git commit -m "feat(ui): CommandPalette renders StatusBadges + nav-action items"
```

---

### Task 8: Portal — status mapping + nav-action group

**Files:**
- Create: `admin/apps/portal/src/components/search/nav-actions.ts`
- Modify: `admin/apps/portal/src/components/AppShellCommandPalette.tsx`
- Test: `admin/apps/portal/src/__tests__/search/AppShellCommandPalette.test.tsx`

**Interfaces:**
- `nav-actions.ts`: `navActions(variant): {label,url}[]` — flatten `nav-config`'s groups→items (and item.children) for the variant into `{label: "Go to <label>", url: href}`.
- `AppShellCommandPalette`: map each hit's `entity_type`→StatusBadge entity + pass `status`; build nav-action items from `navActions(variant)` filtered by a case-insensitive substring of the debounced query, in a "Navigate" group; merge with search-hit groups.

- [ ] **Step 1: Failing test additions**

Extend `AppShellCommandPalette.test.tsx`: a returned hit with `status: "disbursed"`, `entity_type: "loan"` renders its StatusBadge label; typing "bill" surfaces a "Go to Billing" nav action (for the platform variant) that calls `router.push` with the billing route on select. (Mock the search resource + `nav-config` is real.)

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm --filter @sacco/portal test -- AppShellCommandPalette`
Expected: FAIL.

- [ ] **Step 3: Implement**

`nav-actions.ts` flattens `nav-config`. In `AppShellCommandPalette`, map hits to items with `status`/`statusEntity` (entity_type is already the StatusBadge entity for most; map `entity_type`→group label + statusEntity), compute `navItems = navActions(variant).filter(a => a.label.toLowerCase().includes(q)).map(...group:"Navigate")`, and pass `[...navItems, ...hitItems]` (or grouped) to `CommandPalette`. Nav items always show (even on blank query? — only when query non-empty, matching the `enabled` gate; keep consistent: show nav actions when the query matches, alongside hits).

- [ ] **Step 4: Tests + lint + typecheck**

Run: `pnpm --filter @sacco/portal test -- AppShellCommandPalette && pnpm --filter @sacco/portal lint && pnpm --filter @sacco/portal typecheck`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add admin/apps/portal/src/components/search admin/apps/portal/src/components/AppShellCommandPalette.tsx admin/apps/portal/src/__tests__/search
git commit -m "feat(portal): palette status badges + nav-action group from nav-config"
```

---

### Task 9: Close-out — full gates, e2e, CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Full gates**

Run: `venv/bin/ruff check app/core/search/ && venv/bin/mypy app/core/search/ && venv/bin/pytest tests/core/search/ -q` and `cd admin && pnpm lint && pnpm typecheck && pnpm test`.
Expected: all green.

- [ ] **Step 2: End-to-end verification (dev stack + ES + worker)**

Reconcile (worker beat or manual run) indexes all new types for the demo tenant. Rebuild the API if needed. Then: operator ⌘K → a loan/savings account appears with its StatusBadge → Enter navigates; platform ⌘K → an invoice appears; typing "bill" surfaces "Go to Billing" and navigates. Record commands + outputs.

- [ ] **Step 3: CLAUDE.md**

Update the **Search contracts** section: Increment 2 adds loans/savings/applications (operator) + invoices/subscriptions/platform-users (platform), each hit carries a StatusBadge; `types=` narrows within the audience allow-list; a daily delete-sweep removes orphaned ES docs; palette gains nav actions from nav-config. Cross-tenant member search remains explicitly OUT. Increment 2 complete.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): search increment 2 contracts (breadth + sweep + nav actions)"
```

## Out of scope (Increment 3+)

- Cross-tenant member search for platform users.
- Relevance / synonym / typo tuning; event-driven real-time indexing.
- Saved searches, search history, analytics.
