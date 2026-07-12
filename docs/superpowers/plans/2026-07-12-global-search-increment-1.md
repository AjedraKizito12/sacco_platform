# Global Search — Increment 1 (ES Foundation + Thin Slice) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A working ⌘K command palette for platform and operator users, backed by Elasticsearch, that searches tenants (platform) and members (operator) and jumps to the record — proving the full index→query→palette pipeline end to end.

**Architecture:** A watermark reconcile beat bulk-indexes `platform.tenants` and per-schema `members` into per-type ES indices (`sacco_tenants`, `sacco_members`, docs tagged with `tenant_schema`). Permission-scoped query endpoints (`/platform/search` gated support+, `/search` gated tenant-user+gate with a mandatory `tenant_schema` filter) return typed hits. A Dialog-based `CommandPalette` in `@sacco/ui`, driven by a debounced portal client, renders grouped results and navigates on Enter.

**Tech Stack:** Python 3.11, FastAPI, `elasticsearch` (AsyncElasticsearch, already a dep), SQLAlchemy async, Alembic (platform), Celery beat, Next.js 15, `@sacco/ui`/`api-client`/`schemas`, vitest.

**Spec:** `docs/superpowers/specs/2026-07-12-global-search-design.md`

Branch: `feat/search-inc1` (from `main`).

## Global Constraints

- **All backend search code under `app/core/search/`** (cross-cutting; imports nothing from `app/modules`/`app/platform_` except read-only row selects via raw SQL / the active-schema helper).
- **Tenant isolation is absolute:** the operator `/search` endpoint derives the caller's `tenant_schema` SERVER-SIDE (from the tenant session) and ALWAYS ANDs a `term` filter `tenant_schema=<schema>` into the ES query. The client never supplies a schema. Cross-tenant results are impossible.
- **ES is the index; Postgres is the source of truth.** The reconcile beat is the ONLY writer of ES documents. No query path writes to ES.
- **One index per entity type**, tenant-owned docs carry `tenant_schema`; doc id `<schema>:<uuid>` (tenant) or `<uuid>` (platform).
- **Sync = watermark reconcile beat** (`updated_at > last_watermark`); no new domain events, no write-path changes in any module.
- **Platform migration** `013`, `down_revision = "012"` (Phase 4 migration 012 may or may not be merged; if 012 isn't on `main` yet, set `down_revision` to the current platform head — check `alembic/platform/versions/` for the highest revision and depend on it). Offline `alembic upgrade --sql` is broken repo-wide; smoke against a scratch DB.
- **Empty query** (`q` with < 1 non-space char) short-circuits to empty hits with NO ES call.
- ruff + mypy (strict) clean; pnpm lint/typecheck/test clean. Integration tests run against the ES container (`settings.elasticsearch_url`, default `http://localhost:9200`); guard/skip them when ES is unreachable so unit suites stay green offline.
- This increment supersedes PR #72's disabled search stub for platform + operator (the trigger now opens the palette); member stays hidden.

## File Structure

```
alembic/platform/versions/013_search_index_state.py   (create)
app/core/search/__init__.py                            (create)
app/core/search/client.py                              (create: AsyncElasticsearch factory)
app/core/search/indexes.py                             (create: index names + mappings + ensure_indices)
app/core/search/documents.py                           (create: pure row→doc mappers)
app/core/search/models.py                              (create: SearchIndexState)
app/core/search/service.py                             (create: SearchService — bulk_index, query, DSL builder)
app/core/search/reconcile.py                           (create: reconcile beat)
app/core/search/schemas.py                             (create: SearchHitOut, SearchResultsOut)
app/core/search/api.py                                 (create: platform + tenant routers)
app/main.py                                            (modify: mount routers)
app/workers/celery_app.py                              (modify: include + beat_schedule)
tests/core/search/__init__.py                          (create)
tests/core/search/test_documents.py                    (create)
tests/core/search/test_query_builder.py                (create)
tests/core/search/test_reconcile.py                    (create)
tests/core/search/test_api.py                          (create; ES-integration, skip if unreachable)

admin/packages/schemas/src/search.ts                   (create)
admin/packages/schemas/src/index.ts                    (modify: export)
admin/packages/api-client/src/resources/search.ts      (create)
admin/packages/api-client/src/resources/index.ts       (modify: register)
admin/packages/api-client/src/query-keys.ts            (modify: +search keys)
admin/packages/ui/src/components/CommandPalette/*       (create: component + test + story + index)
admin/packages/ui/src/index.ts                         (modify: export)

admin/apps/portal/src/components/AppShellCommandPalette.tsx (create)
admin/apps/portal/src/components/AppShellHeader.tsx    (modify: open palette from trigger)
admin/apps/portal/src/__tests__/search/*               (create)

CLAUDE.md                                              (modify: search contracts)
```

---

### Task 1: Migration + `SearchIndexState` model

**Files:**
- Create: `alembic/platform/versions/013_search_index_state.py`, `app/core/search/__init__.py`, `app/core/search/models.py`
- Test: `tests/core/search/__init__.py`

**Interfaces:**
- Produces: `SearchIndexState` (platform schema) cols `index_name: str pk`, `scope: str pk`, `last_watermark: datetime`, `last_run_at: datetime | None`.

- [ ] **Step 1: Model**

`app/core/search/models.py`:
```python
"""State for the search reconcile beat (platform schema).

One row per (index_name, scope): scope is a tenant schema_name for
tenant-owned entities, or 'platform' for platform entities.
"""
from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SearchIndexState(Base):
    __tablename__ = "search_index_state"
    __table_args__ = {"schema": "platform"}

    index_name: Mapped[str] = mapped_column(Text, primary_key=True)
    scope: Mapped[str] = mapped_column(Text, primary_key=True)
    last_watermark: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
```
`app/core/search/__init__.py`: empty.

- [ ] **Step 2: Migration**

Check the current platform head first: `ls alembic/platform/versions/ | grep -oE '^[0-9]+' | sort -n | tail -1`. Set `down_revision` to that value (expected `012` if Phase 4 merged, else `011`). `alembic/platform/versions/013_search_index_state.py`:
```python
"""Search reconcile watermark state.

Revision: 013
Depends on: <current head>
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP

from alembic import op

revision = "013"
down_revision = "012"  # adjust to the actual current head
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_index_state",
        sa.Column("index_name", sa.Text(), primary_key=True),
        sa.Column("scope", sa.Text(), primary_key=True),
        sa.Column("last_watermark", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_run_at", TIMESTAMP(timezone=True), nullable=True),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_table("search_index_state", schema="platform")
```

- [ ] **Step 3: Smoke the migration**

Run:
```bash
docker compose exec -T postgres psql -U sacco -d sacco -c "CREATE DATABASE search_smoke;"
DATABASE_URL="postgresql+asyncpg://sacco:sacco@localhost:5432/search_smoke" venv/bin/alembic upgrade head
docker compose exec -T postgres psql -U sacco -d search_smoke -c "\dt platform.search_index_state"
docker compose exec -T postgres psql -U sacco -d sacco -c "DROP DATABASE search_smoke;"
```
Expected: `platform.search_index_state` listed.

- [ ] **Step 4: mypy + ruff**

Run: `venv/bin/mypy app/core/search/models.py && venv/bin/ruff check app/core/search/`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add app/core/search/__init__.py app/core/search/models.py alembic/platform/versions/013_search_index_state.py tests/core/search/__init__.py
git commit -m "feat(search): search_index_state model + platform migration 013"
```

---

### Task 2: ES client + indexes + document mappers (pure)

**Files:**
- Create: `app/core/search/client.py`, `app/core/search/indexes.py`, `app/core/search/documents.py`
- Test: `tests/core/search/test_documents.py`

**Interfaces:**
- Produces:
  - `get_search_client() -> AsyncElasticsearch` (from `settings.elasticsearch_url`).
  - `indexes.py`: `TENANTS_INDEX = "sacco_tenants"`, `MEMBERS_INDEX = "sacco_members"`; `INDEX_MAPPINGS: dict[str, dict]`; `async ensure_indices(client) -> None` (create missing, idempotent).
  - `documents.py`: `tenant_document(row) -> dict`, `member_document(schema, row) -> dict`, `doc_id(schema, record_id) -> str`. Each doc has `entity_type`, `record_id`, `tenant_schema` (members only), `title`, `subtitle`, `url`, and searchable fields.

- [ ] **Step 1: Failing mapper tests**

`tests/core/search/test_documents.py`:
```python
from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.core.search.documents import doc_id, member_document, tenant_document


def test_tenant_document_shape():
    tid = uuid.uuid4()
    row = SimpleNamespace(id=tid, name="Demo SACCO", slug="demo-sacco", schema_name="tenant_demo_sacco")
    doc = tenant_document(row)
    assert doc["entity_type"] == "tenant"
    assert doc["record_id"] == str(tid)
    assert doc["title"] == "Demo SACCO"
    assert doc["subtitle"] == "demo-sacco"
    assert doc["url"] == f"/platform/tenants/{tid}"
    assert "tenant_schema" not in doc  # platform entity


def test_member_document_shape_and_scope():
    mid = uuid.uuid4()
    row = SimpleNamespace(
        id=mid, full_name="Grace N", member_number="M-0001",
        email="grace@example.com", phone_number="0700000000",
    )
    doc = member_document("tenant_demo_sacco", row)
    assert doc["entity_type"] == "member"
    assert doc["tenant_schema"] == "tenant_demo_sacco"
    assert doc["title"] == "Grace N"
    assert doc["subtitle"] == "M-0001"
    assert doc["url"] == f"/members/{mid}"
    # searchable fields present
    assert doc["member_number"] == "M-0001"
    assert doc["email"] == "grace@example.com"


def test_doc_id_forms():
    u = uuid.uuid4()
    assert doc_id("tenant_x", u) == f"tenant_x:{u}"
    assert doc_id(None, u) == str(u)
```
(Verify the real `members` columns before implementing — `full_name`, `member_number`, `email`, `phone_number` per `app/modules/members/models.py`; adjust field names if they differ.)

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/pytest tests/core/search/test_documents.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement client, indexes, documents**

`client.py`:
```python
from __future__ import annotations

from elasticsearch import AsyncElasticsearch

from app.core.config import get_settings


def get_search_client() -> AsyncElasticsearch:
    return AsyncElasticsearch(get_settings().elasticsearch_url)
```
`indexes.py`:
```python
from __future__ import annotations

import uuid
from typing import Any

from elasticsearch import AsyncElasticsearch

TENANTS_INDEX = "sacco_tenants"
MEMBERS_INDEX = "sacco_members"

_TEXT = {"type": "text", "fields": {"kw": {"type": "keyword"}}}

INDEX_MAPPINGS: dict[str, dict[str, Any]] = {
    TENANTS_INDEX: {
        "mappings": {"properties": {
            "entity_type": {"type": "keyword"},
            "record_id": {"type": "keyword"},
            "title": _TEXT, "subtitle": _TEXT, "url": {"type": "keyword", "index": False},
            "name": _TEXT, "slug": _TEXT, "schema_name": {"type": "keyword"},
        }}
    },
    MEMBERS_INDEX: {
        "mappings": {"properties": {
            "entity_type": {"type": "keyword"},
            "record_id": {"type": "keyword"},
            "tenant_schema": {"type": "keyword"},
            "title": _TEXT, "subtitle": _TEXT, "url": {"type": "keyword", "index": False},
            "full_name": _TEXT, "member_number": _TEXT, "email": _TEXT, "phone_number": _TEXT,
        }}
    },
}


async def ensure_indices(client: AsyncElasticsearch) -> None:
    for name, body in INDEX_MAPPINGS.items():
        if not await client.indices.exists(index=name):
            await client.indices.create(index=name, body=body)
```
`documents.py`:
```python
from __future__ import annotations

import uuid
from typing import Any


def doc_id(schema: str | None, record_id: uuid.UUID) -> str:
    return f"{schema}:{record_id}" if schema else str(record_id)


def tenant_document(row: Any) -> dict[str, Any]:
    return {
        "entity_type": "tenant",
        "record_id": str(row.id),
        "title": row.name,
        "subtitle": row.slug,
        "url": f"/platform/tenants/{row.id}",
        "name": row.name,
        "slug": row.slug,
        "schema_name": row.schema_name,
    }


def member_document(schema: str, row: Any) -> dict[str, Any]:
    return {
        "entity_type": "member",
        "record_id": str(row.id),
        "tenant_schema": schema,
        "title": row.full_name,
        "subtitle": row.member_number,
        "url": f"/members/{row.id}",
        "full_name": row.full_name,
        "member_number": row.member_number,
        "email": getattr(row, "email", None),
        "phone_number": getattr(row, "phone_number", None),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/core/search/test_documents.py -v`
Expected: PASS.

- [ ] **Step 5: mypy + ruff**

Run: `venv/bin/mypy app/core/search/ && venv/bin/ruff check app/core/search/`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add app/core/search/client.py app/core/search/indexes.py app/core/search/documents.py tests/core/search/test_documents.py
git commit -m "feat(search): ES client, index mappings, document mappers"
```

---

### Task 3: SearchService — query DSL builder + bulk index

**Files:**
- Create: `app/core/search/service.py`
- Test: `tests/core/search/test_query_builder.py`

**Interfaces:**
- Consumes: `get_search_client`, `indexes`, `documents` (Task 2).
- Produces: `SearchService`:
  - `build_query(q: str, *, tenant_schema: str | None) -> dict` — pure ES query body: `multi_match` over the searchable fields; when `tenant_schema` set, wraps in a `bool` with a `filter: [{term: {tenant_schema}}]`. Unit-tested.
  - `async search(indices: list[str], q: str, *, tenant_schema: str | None = None, limit: int = 20) -> list[SearchHit]` — runs the query, maps `_source` → `SearchHit(entity_type,id,title,subtitle,url)`. Empty/blank `q` → `[]` with no ES call.
  - `async bulk_index(index: str, docs: list[tuple[str, dict]]) -> None` — bulk upsert `(doc_id, source)`.
  - `SearchHit` dataclass.

- [ ] **Step 1: Failing query-builder tests**

`tests/core/search/test_query_builder.py`:
```python
from __future__ import annotations

from app.core.search.service import SearchService


def test_build_query_without_schema_has_no_filter():
    body = SearchService.build_query("grace", tenant_schema=None)
    assert "multi_match" in str(body)
    assert "term" not in str(body)  # no tenant filter


def test_build_query_with_schema_ands_tenant_filter():
    body = SearchService.build_query("grace", tenant_schema="tenant_demo_sacco")
    # the term filter pins the schema — tenant isolation
    filters = body["query"]["bool"]["filter"]
    assert {"term": {"tenant_schema": "tenant_demo_sacco"}} in filters


def test_blank_query_is_rejected_before_es(monkeypatch):
    # search() must short-circuit on blank q; assert build is never asked to run.
    import asyncio
    svc = SearchService(client=object())  # client unused for blank q
    out = asyncio.run(svc.search(["sacco_members"], "   "))
    assert out == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/pytest tests/core/search/test_query_builder.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement SearchService**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from elasticsearch.helpers import async_bulk

_FIELDS = ["title^3", "subtitle^2", "full_name", "member_number", "email",
           "phone_number", "name", "slug"]


@dataclass
class SearchHit:
    entity_type: str
    id: str
    title: str
    subtitle: str
    url: str


class SearchService:
    def __init__(self, client: Any) -> None:
        self._es = client

    @staticmethod
    def build_query(q: str, *, tenant_schema: str | None) -> dict[str, Any]:
        match: dict[str, Any] = {
            "multi_match": {
                "query": q,
                "type": "bool_prefix",
                "fields": _FIELDS,
            }
        }
        if tenant_schema is None:
            return {"query": match}
        return {
            "query": {
                "bool": {
                    "must": [match],
                    "filter": [{"term": {"tenant_schema": tenant_schema}}],
                }
            }
        }

    async def search(
        self, indices: list[str], q: str, *,
        tenant_schema: str | None = None, limit: int = 20,
    ) -> list[SearchHit]:
        if len(q.strip()) < 1:
            return []
        body = self.build_query(q.strip(), tenant_schema=tenant_schema)
        body["size"] = limit
        res = await self._es.search(index=",".join(indices), body=body)
        hits: list[SearchHit] = []
        for h in res["hits"]["hits"]:
            s = h["_source"]
            hits.append(SearchHit(
                entity_type=s["entity_type"], id=s["record_id"],
                title=s["title"], subtitle=s.get("subtitle", ""), url=s["url"],
            ))
        return hits

    async def bulk_index(self, index: str, docs: list[tuple[str, dict[str, Any]]]) -> None:
        if not docs:
            return
        actions = [{"_index": index, "_id": did, "_source": src} for did, src in docs]
        await async_bulk(self._es, actions)
```
(`type: "bool_prefix"` gives as-you-type prefix matching for the palette. `async_bulk` is from `elasticsearch.helpers`; confirm the installed client exposes it — the pinned `elasticsearch==8.17.0` does.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/core/search/test_query_builder.py -v`
Expected: PASS.

- [ ] **Step 5: mypy + ruff**

Run: `venv/bin/mypy app/core/search/service.py && venv/bin/ruff check app/core/search/`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add app/core/search/service.py tests/core/search/test_query_builder.py
git commit -m "feat(search): SearchService query builder + bulk index"
```

---

### Task 4: Reconcile beat + watermark

**Files:**
- Create: `app/core/search/reconcile.py`
- Modify: `app/workers/celery_app.py` (include + beat_schedule)
- Test: `tests/core/search/test_reconcile.py`

**Interfaces:**
- Consumes: `SearchService`, `ensure_indices`, document mappers, `SearchIndexState`.
- Produces: `reconcile_search_indexes` Celery task; pure helper `next_watermark(rows, current) -> datetime` (max `updated_at`, defaulting to `current` when no rows) — unit-tested. Active-schema iteration reuses the pattern from `app/core/notifications/beat.py` (`SELECT schema_name FROM platform.tenants WHERE is_active`).

- [ ] **Step 1: Failing watermark test**

`tests/core/search/test_reconcile.py`:
```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.core.search.reconcile import next_watermark


def test_next_watermark_takes_max_updated_at():
    base = datetime(2026, 7, 1, tzinfo=UTC)
    rows = [SimpleNamespace(updated_at=base), SimpleNamespace(updated_at=base + timedelta(hours=2))]
    assert next_watermark(rows, base - timedelta(days=1)) == base + timedelta(hours=2)


def test_next_watermark_keeps_current_when_no_rows():
    base = datetime(2026, 7, 1, tzinfo=UTC)
    assert next_watermark([], base) == base
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/pytest tests/core/search/test_reconcile.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the beat**

`reconcile.py` — mirror `app/core/notifications/beat.py`'s engine/session + active-schema handling. `next_watermark` is the pure helper. The task: `ensure_indices`; reconcile `sacco_tenants` (scope `platform`, from `platform.tenants`); reconcile `sacco_members` per active schema (scope=schema). Each reconcile: read `last_watermark` from `platform.search_index_state` (default epoch), `SELECT ... WHERE updated_at > :wm ORDER BY updated_at`, map to docs, `bulk_index`, upsert the state row with `next_watermark` + `last_run_at=now()`. Register in `celery_app.py`:
```python
# include:
"app.core.search.reconcile",
# beat_schedule:
"reconcile-search-indexes": {
    "task": "app.core.search.reconcile.reconcile_search_indexes",
    "schedule": 45.0,
},
```
(Use `EPOCH = datetime(1970,1,1,tzinfo=UTC)` as the default watermark for first-run backfill. Follow the notifications beat's `asyncio.run` + `create_async_engine` + dispose pattern; do watermark comparison in Python if asyncpg tz-compare bites, per the notifications gotcha.)

- [ ] **Step 4: Run tests + verify a live reconcile indexes rows**

Run: `venv/bin/pytest tests/core/search/test_reconcile.py -v`
Expected: PASS.
Then a live smoke (ES + demo data up): run the task body once and confirm docs land:
```bash
venv/bin/python -c "from app.core.search.reconcile import reconcile_search_indexes as t; t()"
curl -s "localhost:9200/sacco_members/_count" ; echo; curl -s "localhost:9200/sacco_tenants/_count"
```
Expected: non-zero counts (demo tenant + its members indexed).

- [ ] **Step 5: mypy + ruff**

Run: `venv/bin/mypy app/core/search/reconcile.py && venv/bin/ruff check app/core/search/`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add app/core/search/reconcile.py app/workers/celery_app.py tests/core/search/test_reconcile.py
git commit -m "feat(search): watermark reconcile beat for tenants + members"
```

---

### Task 5: Query API — platform + tenant routers

**Files:**
- Create: `app/core/search/schemas.py`, `app/core/search/api.py`
- Modify: `app/main.py` (mount both routers)
- Test: `tests/core/search/test_api.py` (ES-integration; skip when ES unreachable)

**Interfaces:**
- Consumes: `SearchService`, `get_search_client`, `TENANTS_INDEX`/`MEMBERS_INDEX`; `CurrentSupport` (`app.platform_.auth`), `CurrentTenantUser` + `get_tenant_session` (tenant schema resolution).
- Produces: `SearchHitOut {entity_type,id,title,subtitle,url}`, `SearchResultsOut {hits, took_ms}`; `platform_search_router` (`GET /platform/search`), `tenant_search_router` (`GET /search`).

- [ ] **Step 1: Schemas**

`schemas.py`:
```python
from __future__ import annotations

from pydantic import BaseModel


class SearchHitOut(BaseModel):
    entity_type: str
    id: str
    title: str
    subtitle: str
    url: str


class SearchResultsOut(BaseModel):
    hits: list[SearchHitOut]
    took_ms: int
```

- [ ] **Step 2: Failing API/isolation test**

`tests/core/search/test_api.py` — mark the module to skip if ES is unreachable (`pytest.importorskip` won't help; ping ES in a module fixture and `pytest.skip` on failure). Seed two schemas' members + one tenant into ES via `SearchService.bulk_index`, then: (a) operator query with schema A returns only A's member; (b) same query with schema B returns only B's; (c) platform query returns the tenant; (d) blank `q` → empty. Use dependency overrides for `CurrentSupport`/`CurrentTenantUser` and to inject the caller's schema (mirror the tenant-session override in `tests/platform_/tenant_users_admin/test_api.py`).
```python
# core assertion of the isolation guarantee:
async def test_operator_search_is_schema_isolated(es_ready, seeded):
    a = await client.get("/search", params={"q": "grace"}, headers=schema_a_headers)
    assert all(h["entity_type"] == "member" for h in a.json()["hits"])
    # the seeded member in schema B must NOT appear for schema A
    assert seeded["b_member_id"] not in [h["id"] for h in a.json()["hits"]]
```

- [ ] **Step 3: Run to verify it fails**

Run: `venv/bin/pytest tests/core/search/test_api.py -v`
Expected: FAIL (routers missing) — or SKIP if ES down (then run with ES up).

- [ ] **Step 4: Implement the API**

`api.py`:
```python
"""Search query endpoints. Operator queries are schema-isolated server-side."""
from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.core.db import get_tenant_session
from app.core.search.client import get_search_client
from app.core.search.indexes import MEMBERS_INDEX, TENANTS_INDEX
from app.core.search.schemas import SearchHitOut, SearchResultsOut
from app.core.search.service import SearchService
from app.modules.iam.dependencies import CurrentTenantUser
from app.platform_.auth import CurrentSupport

platform_search_router = APIRouter(prefix="/platform/search", tags=["search"])
tenant_search_router = APIRouter(prefix="/search", tags=["search"])


def _results(hits, started: float) -> SearchResultsOut:
    return SearchResultsOut(
        hits=[SearchHitOut(entity_type=h.entity_type, id=h.id, title=h.title,
                           subtitle=h.subtitle, url=h.url) for h in hits],
        took_ms=int((time.perf_counter() - started) * 1000),
    )


@platform_search_router.get("", response_model=SearchResultsOut)
async def platform_search(_user: CurrentSupport, q: str = Query(""), limit: int = Query(20, le=50)) -> SearchResultsOut:
    started = time.perf_counter()
    es = get_search_client()
    try:
        hits = await SearchService(es).search([TENANTS_INDEX], q, limit=limit)
    finally:
        await es.close()
    return _results(hits, started)


TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]


@tenant_search_router.get("", response_model=SearchResultsOut)
async def tenant_search(
    session: TenantSession, _user: CurrentTenantUser,
    q: str = Query(""), limit: int = Query(20, le=50),
) -> SearchResultsOut:
    started = time.perf_counter()
    # Resolve the caller's schema from the tenant session (server-side, never
    # client). PREFER a first-class accessor if get_tenant_session exposes one
    # (e.g. session.info["tenant_schema"] or a request-state value — check
    # app/core/db.py). Fall back to reading it off the session's search_path:
    #   from sqlalchemy import text
    #   row = (await session.execute(text("SHOW search_path"))).scalar()
    #   schema = str(row).split(",")[0].strip().strip('"')
    schema = await _resolve_tenant_schema(session)
    es = get_search_client()
    try:
        hits = await SearchService(es).search([MEMBERS_INDEX], q, tenant_schema=schema, limit=limit)
    finally:
        await es.close()
    return _results(hits, started)
```
(Verify the cleanest way to read the active schema from the tenant session — the repo resolves tenant schema in `get_tenant_session`; if a helper or request-state value exposes it, use that instead of `SHOW search_path`. The requirement is server-derived schema.) Mount both routers in `app/main.py` beside the others.

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/pytest tests/core/search/test_api.py -v` (ES up)
Expected: PASS incl. the isolation assertion.

- [ ] **Step 6: mypy + ruff + full search suite**

Run: `venv/bin/mypy app/core/search/ && venv/bin/ruff check app/core/search/ && venv/bin/pytest tests/core/search/ -q`
Expected: clean, green (integration tests skip cleanly if ES down).

- [ ] **Step 7: Commit**

```bash
git add app/core/search/schemas.py app/core/search/api.py app/main.py tests/core/search/test_api.py
git commit -m "feat(search): schema-isolated /search + /platform/search endpoints"
```

---

### Task 6: `@sacco/schemas` + api-client search resource

**Files:**
- Create: `admin/packages/schemas/src/search.ts`, `admin/packages/api-client/src/resources/search.ts`
- Modify: `admin/packages/schemas/src/index.ts`, `admin/packages/api-client/src/resources/index.ts`, `admin/packages/api-client/src/query-keys.ts`
- Test: `admin/packages/api-client/src/__tests__/query-keys-search.test.ts`

**Interfaces:**
- Produces: `SearchHitOut {entity_type,id,title,subtitle,url}`, `SearchResultsOut {hits,took_ms}` (schemas); `search(api)` resource with `platformSearch(q)`, `tenantSearch(q)`; query keys `search.platform(q)`, `search.tenant(q)`.

- [ ] **Step 1: Failing query-keys test**

`query-keys-search.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { queryKeys } from "../query-keys";
describe("search query keys", () => {
  it("scoped by audience + query", () => {
    expect(queryKeys.search.platform("ab")).toEqual(["search", "platform", "ab"]);
    expect(queryKeys.search.tenant("ab")).toEqual(["search", "tenant", "ab"]);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd admin && pnpm --filter @sacco/api-client test -- query-keys-search`
Expected: FAIL.

- [ ] **Step 3: Implement**

`schemas/src/search.ts`:
```ts
export interface SearchHitOut {
  entity_type: string;
  id: string;
  title: string;
  subtitle: string;
  url: string;
}
export interface SearchResultsOut {
  hits: SearchHitOut[];
  took_ms: number;
}
```
Export from `schemas/index.ts`. `api-client/src/resources/search.ts`:
```ts
import type { FetchClient } from "../client";
export function search(api: FetchClient) {
  return {
    platformSearch: (q: string) =>
      api.GET("/platform/search" as never, { params: { query: { q } } } as never),
    tenantSearch: (q: string) =>
      api.GET("/search" as never, { params: { query: { q } } } as never),
  } as const;
}
```
Register in `resources/index.ts`. Query keys:
```ts
  search: {
    root: () => ["search"] as const,
    platform: (q: string) => ["search", "platform", q] as const,
    tenant: (q: string) => ["search", "tenant", q] as const,
  },
```

- [ ] **Step 4: Tests + lint + typecheck**

Run: `pnpm --filter @sacco/api-client test -- query-keys-search && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/api-client lint && pnpm --filter @sacco/api-client typecheck`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add admin/packages/schemas/src/search.ts admin/packages/schemas/src/index.ts admin/packages/api-client/src/resources/search.ts admin/packages/api-client/src/resources/index.ts admin/packages/api-client/src/query-keys.ts admin/packages/api-client/src/__tests__/query-keys-search.test.ts
git commit -m "feat(search): schemas wire types + api-client search resource"
```

---

### Task 7: `@sacco/ui` CommandPalette

**Files:**
- Create: `admin/packages/ui/src/components/CommandPalette/{CommandPalette.tsx,CommandPalette.test.tsx,CommandPalette.stories.tsx,index.ts}`
- Modify: `admin/packages/ui/src/index.ts`

**Interfaces:**
- Produces: `CommandPalette` — Dialog-based, presentational, controlled:
```ts
interface CommandPaletteItem { id: string; title: string; subtitle: string; url: string; group: string; }
interface CommandPaletteProps {
  open: boolean;
  onOpenChange(open: boolean): void;
  query: string;
  onQueryChange(q: string): void;
  items: CommandPaletteItem[];
  loading?: boolean;
  onSelect(item: CommandPaletteItem): void;
  emptyLabel?: string;   // default "No results"
  placeholder?: string;  // default "Search…"
}
```
Renders a search input (autofocused), grouped list (by `item.group`), roving keyboard nav (↑/↓ move active, Enter selects active, Esc closes), a loading row, and the empty state (only when `query` non-empty and not loading).

- [ ] **Step 1: Failing vitest**

`CommandPalette.test.tsx`: renders items grouped; typing calls `onQueryChange`; ArrowDown+Enter selects the active item (`onSelect`); Esc calls `onOpenChange(false)`; empty state shows `emptyLabel` when query set and no items. Build on `@testing-library` + `userEvent` keyboard.

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm --filter @sacco/ui test -- CommandPalette`
Expected: FAIL.

- [ ] **Step 3: Implement** on the existing `Dialog` primitive (import from `../Dialog`), using design tokens only (contract Q). Keyboard: track an `activeIndex` over the flattened item list; ArrowUp/Down clamp; Enter → `onSelect(items[activeIndex])`; input `autoFocus`. Group headers from distinct `item.group` values in order. Export from `index.ts` + `ui/src/index.ts`.

- [ ] **Step 4: Storybook story** (default / loading / empty / grouped variants).

- [ ] **Step 5: Tests + lint + typecheck**

Run: `pnpm --filter @sacco/ui test -- CommandPalette && pnpm --filter @sacco/ui lint && pnpm --filter @sacco/ui typecheck`
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add admin/packages/ui/src/components/CommandPalette admin/packages/ui/src/index.ts
git commit -m "feat(ui): CommandPalette (Dialog-based, keyboard-navigable)"
```

---

### Task 8: Portal wiring + close-out

**Files:**
- Create: `admin/apps/portal/src/components/AppShellCommandPalette.tsx`, `admin/apps/portal/src/__tests__/search/AppShellCommandPalette.test.tsx`
- Modify: `admin/apps/portal/src/components/AppShellHeader.tsx`, `CLAUDE.md`

**Interfaces:**
- Consumes: `CommandPalette` (Task 7), `resources.search` + `queryKeys.search` (Task 6), `useAuth`, `useRouter`.
- Produces: `AppShellCommandPalette({ variant })` — owns open state + global ⌘K/Ctrl-K listener; debounces `query` (~200ms); TanStack `useTypedQuery` on `queryKeys.search[variant==="platform"?"platform":"tenant"](debounced)` calling the matching resource (enabled only when query non-empty); maps hits → grouped items (group = entity_type label); `onSelect` → `router.push(item.url)` + close. Header wires the `CommandPaletteTrigger` `onActivate` to open it (platform + operator), replacing the disabled stub; member stays null.

- [ ] **Step 1: Failing portal test**

`AppShellCommandPalette.test.tsx` (mock `@/auth/use-auth`, `next/navigation`, QueryClient wrapper): pressing ⌘K opens the palette; typing triggers the search resource with the query; selecting a result calls `router.push` with the hit url. Mirror `AppShellNotificationBell.test.tsx` patterns.

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm --filter @sacco/portal test -- AppShellCommandPalette`
Expected: FAIL.

- [ ] **Step 3: Implement** the client component + header wiring. Header: keep `CommandPaletteTrigger` for platform/operator but pass a real `onActivate` that opens the palette (drop the `disabled` prop for those variants); render `<AppShellCommandPalette variant={variant} />` alongside. Member: unchanged (null).

- [ ] **Step 4: Run tests + lint + typecheck**

Run: `pnpm --filter @sacco/portal test -- AppShellCommandPalette && pnpm --filter @sacco/portal lint && pnpm --filter @sacco/portal typecheck`
Expected: green.

- [ ] **Step 5: End-to-end verification (dev stack + ES)**

With the worker/beat running (so a reconcile has indexed the demo tenant + members): log in as the platform superuser, ⌘K, type the demo tenant name → the tenant appears → Enter navigates to its detail page. Log in as the demo operator, ⌘K, type a member name → only that tenant's members appear → Enter → member detail. Record in the task report.

- [ ] **Step 6: Full gates + CLAUDE.md**

Run: `venv/bin/ruff check app/core/search/ && venv/bin/mypy app/core/search/ && venv/bin/pytest tests/core/search/ -q` and `cd admin && pnpm lint && pnpm typecheck && pnpm test`.
CLAUDE.md — add a **Search contracts** subsection: all search code in `app/core/search/`; ES is the index and Postgres the source of truth; the reconcile beat is the only writer of ES docs; operator `/search` is schema-isolated server-side (mandatory `tenant_schema` filter); `/search` + `/platform/search` are the only query surfaces; Increment 2 (breadth: loans/savings/invoices/etc., nav actions, deletes) pending. Note the scope exception (adds `app/core/search/`, platform migration 013, palette portal code). Roadmap/feature note that search Increment 1 (tenants + members) is done.

- [ ] **Step 7: Commit**

```bash
git add admin/apps/portal/src/components/AppShellCommandPalette.tsx admin/apps/portal/src/components/AppShellHeader.tsx admin/apps/portal/src/__tests__/search CLAUDE.md
git commit -m "feat(portal): ⌘K command palette wired to search (platform + operator)"
```

## Out of scope (Increment 2 — reminder)

- Loans, savings accounts, loan applications, invoices, subscriptions, platform users.
- Palette quick-nav actions; relevance/ranking tuning; typo tolerance.
- Hard-delete/tombstone handling; cross-tenant member search for platform.
- Member-audience search.
