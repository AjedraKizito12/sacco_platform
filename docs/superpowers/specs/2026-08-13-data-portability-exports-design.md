# Phase 8 — Data Portability & Member Exports — Design Spec

- **Date:** 2026-08-13
- **Phase:** 8 of the SaaS launch roadmap (public-launch blocker; depends on P3 Notifications)
- **Status:** Approved design, pending implementation plan

## 1. Business Objective

Uganda's Tier 4 Microfinance Act requires SACCO members to receive their own
records on demand. The reporting module covers SACCO-level reports; individual
member portability is missing. This phase adds **asynchronous, multi-format
exports of member-scoped data** — requestable by operators *and* by members
themselves.

## 2. Scope

**In scope**
- Export types (all four): `savings_statement`, `loan_statement`,
  `share_statement`, `full_record` (combined).
- Formats (all three): `pdf` (human-readable), `xlsx` (accountant-friendly),
  `csv` (machine-readable).
- Two requesting audiences: tenant operators and members (self-service).
- Async request → job → notification → authenticated download.
- 30-day retention, then auto-delete of the stored bytes.

**Out of scope (v1)**
- Detached, shareable signed download URLs (email-a-link). Deferred until a real
  notification provider ships; download is authenticated instead. The endpoint
  is designed so an HMAC-signed token variant can be added without a schema
  change.
- Object-storage backend (S3/MinIO). Deferred behind the `ExportStorage`
  interface.
- Cross-tenant / platform-operator export surfaces. Exports are tenant-scoped.
- Bulk / all-members exports. One member per request.

## 3. Deliberate deviations from the roadmap

The roadmap (`docs/superpowers/plans/saas-launch-roadmap.md`, §Phase 8) is
amended by this spec in four places, each for a stated reason:

1. **Module path:** `app/modules/exports/`, **not** `app/platform_/exports/`.
   `member_exports` is a tenant-schema table and the source data
   (savings/loans/shares/fees) is tenant-scoped. Platform schema is wrong for
   tenant data. Exports is a proper tenant bounded-context module.
2. **Member self-service included.** The roadmap deferred member-facing exports;
   this phase includes a `/member/exports*` router because the regulatory driver
   ("members receive their own records on demand") is member-centric and the
   member portal already exists.
3. **Storage is Postgres `bytea`,** not object storage. Member exports are small
   (one member's records); the app has never wired an S3 client and deliberately
   keeps S3 credentials out of its image (backups/offboarding archival are
   infra-side only). Retention-delete stays atomic with the row.
4. **Download is authenticated,** not a 1h signed URL. Both audiences reach
   downloads through their authenticated portal; there is no shareable URL to
   leak. Signed-token links are a forward extension behind the same endpoint.

## 4. Architecture

Exports is a thin orchestration layer — **queue → aggregate → render → store →
notify** — over the existing `reporting` module's aggregation services.

```
POST /exports/... or /member/exports
        │  (writes member_exports row, status=queued, 202)
        ▼
member_exports (tenant schema, queued)
        │
process_export_queue beat (60s, FOR UPDATE SKIP LOCKED, per-schema)
        │  set processing
        ├─► reporting service interfaces  →  aggregated data
        │      MemberStatementService (full_record)
        │      per-type statement services (savings/loan/share)
        ├─► ExportRenderer (pdf | xlsx | csv)  →  bytes
        ├─► ExportStorage.store()  →  member_exports.file_bytes + checksum
        ├─► status=ready, available_until=now+30d, completed_at
        └─► NotificationService.publish(member_export_ready | _failed)
        ▼
GET /exports/{id}/download  (authenticated + ownership)  →  streamed attachment
        │
expire_old_exports beat (daily)  →  status=expired, file_bytes=NULL
```

**Isolation / testability**
- Renderers are pure `(data) → (bytes, file_name, mime)` — no DB, no I/O.
- `ExportStorage` is an interface; `PostgresExportStorage` is the v1 impl.
- Data aggregation is delegated to `reporting` service interfaces — exports
  imports no other module's models (CLAUDE.md cross-module rule).
- The worker runs per-tenant-schema with per-schema failure isolation, matching
  the search-reconcile and offboarding-sweep patterns.

## 5. Data model

New table, **tenant schema**, declared with **no** `__table_args__` schema
(resolved at runtime via `search_path`):

```
member_exports
  id                 uuid  pk
  member_id          uuid  not null  references members(id)
  requested_by_type  text  not null            -- 'tenant_user' | 'member'
  requested_by_id    uuid  not null            -- requester id (no cross-audience FK)
  export_type        text  not null            -- 'savings_statement'|'loan_statement'|'share_statement'|'full_record'
  format             text  not null            -- 'pdf'|'xlsx'|'csv'
  filters            jsonb not null default '{}'::jsonb   -- {"from_date":..,"to_date":..}
  status             text  not null default 'queued'
                     -- 'queued'|'processing'|'ready'|'failed'|'expired'|'cancelled'
  file_bytes         bytea                       -- the artifact; NULL until ready, NULL again on expiry
  file_name          text                        -- e.g. 'savings_statement_2026-01.pdf'
  file_size_bytes    bigint
  checksum           text                        -- sha256 hex of file_bytes
  available_until    timestamptz                 -- completed_at + 30d
  failure_reason     text
  idempotency_key    text  not null              -- unique; per CLAUDE.md retry rule
  created_at         timestamptz not null default now()
  started_at         timestamptz
  completed_at       timestamptz

  index  ix_member_exports_status_created  (status, created_at)   -- worker pickup
  unique uq_member_exports_idempotency_key (idempotency_key)
```

Migration lives in `alembic/tenant/` (per-tenant schema).

`requested_by_type` replaces the roadmap's single `requested_by → tenant_users`
FK because a member requester is not a `tenant_user`.

## 6. API surface

### 6.1 Operator router (`app/modules/exports/api.py`)

Gated by `CurrentTenantUser` + subscription gate.

| Method | Path | Purpose | Gate |
|---|---|---|---|
| POST | `/exports/members/{member_id}` | Request an export for a member | `exports.create`; may export any member in the caller's tenant (operator visibility is permission-gated, not per-member — matching the rest of the operator surface). Unknown member id → 404 |
| GET | `/exports` | List requests (paginated; `?member_id=`, `?status=`) | `exports.read` |
| GET | `/exports/{id}` | Status + metadata (+ download path if ready) | tenant scope |
| GET | `/exports/{id}/download` | Stream the artifact | ownership |
| DELETE | `/exports/{id}` | Cancel a **queued** export (409 if processing) | requester or admin |

### 6.2 Member self-service router (`/member/exports*`)

Gated by `CurrentMember` + subscription gate. **Always** scoped to
`current_member.id`; the router never accepts a client-supplied member id.
Cross-member access → **404** (member-contract rule).

`POST /member/exports` · `GET /member/exports` · `GET /member/exports/{id}` ·
`GET /member/exports/{id}/download` · `DELETE /member/exports/{id}`

### 6.3 Request / response

```
POST body (both audiences; operator path also carries member_id in the URL)
{
  "export_type": "savings_statement"|"loan_statement"|"share_statement"|"full_record",
  "format":      "pdf"|"xlsx"|"csv",
  "from_date":   "2026-01-01",   // optional
  "to_date":     "2026-01-31"    // optional
}
Idempotency-Key: <uuid>         // required header (auto-injected by portal client)

202 Accepted
{ "id": "...", "status": "queued", "status_url": "/exports/{id}" }
```

`from_date > to_date` → 422. Unknown enum values → 422.

## 7. Async pipeline

Two Celery beats registered in `app/workers/celery_app.py`:

| Job | Schedule | Behavior |
|---|---|---|
| `process_export_queue` | every 60s | Per tenant schema: `SELECT ... FOR UPDATE SKIP LOCKED` the oldest `queued` rows → `processing` → aggregate via reporting service → render → `ExportStorage.store()` + checksum + size → `ready`, `available_until = now()+30d`, `completed_at`. On exception → `failed` + `failure_reason`. Publish `member_export_ready` / `member_export_failed`. Per-schema failure isolation. |
| `expire_old_exports` | daily | `ready` rows with `available_until < now()` → `status='expired'`, `file_bytes=NULL`. |

Cancellation is **queued-only**: `processing` is short-lived (60s cycle), so
DELETE on a `processing`/terminal row returns 409 rather than racing the worker.

## 8. Renderers

One protocol, three implementations, selected by `format`. Pure functions:

```
ExportRenderer.render(export_type, data) -> (bytes, file_name, mime)
  PdfRenderer   WeasyPrint + Jinja (reuse reporting statement templates;
                full_record = the existing consolidated layout)
  XlsxRenderer  openpyxl; one sheet per section (Savings/Loans/Shares/Fees),
                tabular money, a header metadata block
  CsvRenderer   stdlib csv; full_record is multi-section (section header rows)
```

Data is produced by `reporting` service interfaces (`MemberStatementService`
for `full_record`; the per-type statement services for the three individual
types), filtered by `filters.from_date/to_date`.

**Confidentiality watermark** (all formats): `Confidential — issued to
{requester_email} on {date}` — PDF footer, XLSX header block, CSV leading
comment row. Money is DECIMAL(19,4)-formatted, never float; tabular numerals in
xlsx.

## 9. Storage abstraction

```
ExportStorage:
    store(export_id, data: bytes) -> storage_key
    load(export_id) -> bytes
    delete(export_id) -> None

PostgresExportStorage (v1)  — reads/writes member_exports.file_bytes
```

`storage_key` is reserved for a future S3 impl; for Postgres it is the row id.

## 10. Notifications

Two new Phase-3 event codes (catalog row + template seed + portal catalog
mirror row each, per the notifications increment-3 pattern):

- `member_export_ready` — recipient = the requester (`tenant_user` or
  `member`); in-app feed item; context carries `export_type` + the status/
  download path only. **No PII or secrets** (allow-list enforced at publish).
- `member_export_failed` — same recipient; context carries `export_type` +
  `failure_reason` summary.

Published via `NotificationService.publish()` inside the worker's transaction.

## 11. Security

| Threat | Mitigation |
|---|---|
| Exports leak across members | Member router scoped to `current_member.id`, never a client id; cross-member → 404. Operator access is `exports.create`-gated (permission, not per-member); a tenant operator can only ever reach members within their own tenant schema (search_path isolation). |
| Download URL leaked | No shareable URL — `GET .../{id}/download` requires the requester's JWT + ownership check. |
| PII indexed by a search engine | Artifact lives in the private DB (bytea), never a public bucket; served only through the authed endpoint. |
| Confidential doc mishandled | Every artifact watermarks `issued to {email} on {date}`. |
| Stale data retained forever | `expire_old_exports` nulls `file_bytes` after 30 days; delete is atomic with the row. |

## 12. Portal surfaces (`admin/apps/portal`)

- **Operator:** `/members/[id]/exports` (request form + per-member history) and a
  top-level `/exports` list across members. Both via `<DataTable>` with a new
  `member_export` entry in `StatusBadge/status-maps.ts`.
- **Member:** `/member/exports` (request own + history), reached from member nav
  (new "Exports" item beside "Statements").
- **Forms:** `<FormField>` + Zod schema in `@sacco/schemas`; `<DateRangeInput>`
  for the filter; `export_type` / `format` via shadcn `<Select>`. Download goes
  through a Next.js proxy route that attaches the server-side Bearer token
  (mirrors `/api/member/statement`). `Idempotency-Key` auto-injected (contract
  L).
- **Schemas / api-client:** new `exports` resource + query-keys in
  `@sacco/api-client`; `member_export` types in `@sacco/schemas`.

## 13. New dependency

- **`openpyxl`** — pure-Python, well-maintained xlsx writer. Justified in the
  adding commit per CLAUDE.md's "no new top-level deps without justification"
  rule: Excel export is a named requirement ("accountants love it") and there is
  no existing xlsx tooling in the tree.

## 14. Testing

- **Renderers:** pure unit tests — feed a fixture aggregate, assert bytes are a
  valid PDF/xlsx/CSV and contain the watermark + key figures.
- **Service:** request creation (idempotency, validation, scope), the worker
  transition (`queued→processing→ready`, `→failed`), expiry.
- **API:** operator + member routers — scope/ownership (cross-member 404),
  gating, 202 shape, 409 cancel-while-processing, 422 bad range.
- **Integration:** real Postgres; end-to-end request → run worker → download
  bytes → checksum matches.
- **Notifications:** `member_export_ready`/`_failed` published to the correct
  recipient with no PII in context.

## 15. Contracts to add to CLAUDE.md (on completion)

An "Exports module contracts (Phase 8)" section stating: `MemberExportService`
is the only writer of `member_exports`; the worker beat is the only code that
transitions `queued→processing→ready/failed`; download is authenticated (no
shareable URL) in v1; storage is Postgres-bytea behind `ExportStorage`;
renderers are pure; exports consumes `reporting` service interfaces only (no
cross-module model imports); member router is always self-scoped (cross-member
404).
