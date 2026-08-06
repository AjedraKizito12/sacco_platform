# Phase 7 — Tenant Offboarding & Retention: Design

**Status:** approved (brainstorm 2026-08-05)
**Roadmap:** SaaS launch Phase 7 (`docs/superpowers/plans/saas-launch-roadmap.md` §Phase 7)
**Gate:** public launch. Depends on Phase 1 (billing), Phase 3 (notifications), Phase 4 (infra archival pattern).

## Problem

A SaaS without a clean offboarding story either lets cancelled tenants
accumulate forever (data + cost + liability) or hard-deletes them instantly
(legal + customer-relationship risk). Phase 7 establishes a **staged,
reversible-until-archived lifecycle** from cancellation to deletion, with a
full audit trail, customer communication at each step, and a pre-deletion
encrypted archive that survives schema drop.

## Lifecycle

```
active → cancelled → read_only → archived → hard_deleted
   ↑_________|__________|            |
        restore (until archived)     └─ physical dump+drop is infra-side
```

- **cancelled** — offboarding initiated; billing stopped. Full 403 at the gate.
- **read_only** — grace window: the customer can still *view/export* their
  data but not mutate it.
- **archived** — schema has been (or is being) dumped to encrypted object
  storage and dropped. Full 403.
- **hard_deleted** — archive object deleted after long-term retention (7y).

Default cadence: `cancelled → read_only` at +7 days, `read_only → archived` at
+83 days (90 days total from cancellation), `archived → hard_deleted` at +7
years. Windows are settings; per-tenant legal holds push the deadline out.

## Key decisions (locked in brainstorm)

1. **App owns the state machine; physical archival is infra-side** (Phase-4
   split). The app records archival *telemetry* and the "ready to archive"
   signal; a host-side script does `pg_dump → encrypt → upload → DROP SCHEMA`.
   S3 credentials, `pg_dump`, and destructive DDL stay **out of the app image**
   — the app has never had an object-storage client or dropped a schema, and
   Phase 4 established this exact split for backups.
2. **`read_only` is enforced method-aware at the gate**: safe methods
   (`GET/HEAD/OPTIONS`) pass, writes → 403.
3. **Maker-checker**: `cancel` requires quorum 2; `restore` and
   `extend-retention` are direct (mirrors today's `suspend`(MC)/`reactivate`
   (direct)).
4. **Retention config**: global settings for window lengths + a per-tenant
   `retention_hold_until` timestamp set by `extend-retention`. **No**
   `retention_policy` enum.
5. **A dedicated `lifecycle_state` column**, separate from `status`
   (provisioning) and `subscription_status` (billing gate) — the three
   concerns are not conflated.
6. **In-app archive download is cut.** The app has no S3 credentials, so it
   cannot mint a signed URL. It exposes `archive_storage_key`; retrieval is a
   documented operator runbook (like Phase 4 restore).

## Data model (platform migration 015)

`ALTER platform.tenants ADD`:

| Column | Type | Notes |
|---|---|---|
| `lifecycle_state` | text NOT NULL default `'active'` | CHECK in (active, cancelled, read_only, archived, hard_deleted) |
| `cancelled_at` | timestamptz null | |
| `read_only_at` | timestamptz null | |
| `archived_at` | timestamptz null | set by the app when scheduling archival |
| `hard_deleted_at` | timestamptz null | |
| `retention_hold_until` | timestamptz null | legal hold; blocks the read_only→archived transition while in the future |
| `archive_storage_key` | text null | set by the infra script |
| `archive_size_bytes` | bigint null | set by the infra script |
| `archive_checksum` | text null | set by the infra script; NULL = physical dump not yet done |

New table `platform.tenant_lifecycle_events` (append-only audit, one row per
transition):

```
id           uuid pk
tenant_id    uuid not null references platform.tenants(id)
from_state   text not null
to_state     text not null
occurred_at  timestamptz not null default now()
reason       text
actor_id     uuid null references platform.platform_users(id)  -- null for beat-driven
metadata     jsonb not null default '{}'
```

No tenant-schema changes. No `alembic/tenant/` migration.

## State machine & ownership

`OffboardingService` (`app/platform_/tenants/offboarding_service.py`) is the
ONLY writer of `lifecycle_state` and the `*_at` / `retention_hold_until`
columns, and the ONLY inserter of `tenant_lifecycle_events`. This extends the
existing contract ("only `TenantService` mutates tenant columns") — the two
services are siblings in `app/platform_/tenants/`; `lifecycle_state` is added
to that contract's column list. Every transition writes a lifecycle event in
the same transaction.

| Transition | Trigger | Auth | Effect |
|---|---|---|---|
| `active → cancelled` | operator | **maker-checker q=2** (`tenant.cancel`) | set `cancelled_at`; stop billing via `SubscriptionService.cancel(hard)`; notify |
| `{cancelled,read_only,archived} → active` | operator | direct (superuser) | **restore**; clear the offboarding timestamps; notify. Allowed only while `archive_checksum IS NULL` (schema still present) |
| set `retention_hold_until` | operator | direct (superuser) | **extend-retention** (legal hold); notify |
| `cancelled → read_only` | beat (daily) | system | at `cancelled_at + OFFBOARDING_READ_ONLY_DAYS`; set `read_only_at`; notify |
| `read_only → archived` | beat (daily) | system | at `read_only_at + OFFBOARDING_ARCHIVE_DAYS`, **unless `retention_hold_until` is in the future**; set `archived_at`; notify. Physical dump/drop happens infra-side afterward |
| `archived → hard_deleted` | beat (daily) | system | at `archived_at + 7y`; set `hard_deleted_at`. Infra deletes the archive object |

**Restore boundary:** restore is allowed up to and including `archived` *only
while the schema still exists* (`archive_checksum IS NULL`). Once the infra
script has physically dumped+dropped the schema (`archive_checksum` set),
restore is rejected (409) — recovery is then a runbook restore-from-archive,
not an API action. This is the honest boundary given the Phase-4 split.

Billing coupling: offboarding `cancel` stops billing by hard-cancelling the
subscription via `SubscriptionService.cancel(cancel_at_period_end=False)`.
The billing contract currently restricts that hard-cancel path to the
`billing.cancel_subscription` executor, so Phase 7 **amends that contract to
also permit the `tenant.cancel` executor** as a caller — the offboarding cancel
has already cleared quorum-2 maker-checker, so it is an authorized, audited
path, not an "admin override." `subscription_status` remains owned solely by
`SubscriptionService` (`OffboardingService` never writes it directly); the two
transitions run in one DB transaction so billing and offboarding state move
together.

**Restore does not auto-re-establish billing.** Restoring `→ active` clears the
offboarding timestamps and lifecycle state only; a hard-cancelled subscription
is not silently un-cancelled (that would conflate offboarding recovery with a
billing decision). If the tenant should bill again, the operator re-establishes
it through the existing `assign-plan` flow. Until then the tenant is `active`
in lifecycle terms but `subscription_status` reflects the cancelled billing —
the existing subscription gate governs access exactly as it does for any
plan-less tenant. This keeps the two concerns cleanly separable.

## Gate enforcement (`app/core/db.py:get_tenant_session`)

The gate query additionally selects `lifecycle_state`, checked **before** the
existing `subscription_status` logic. `request.method` is already available in
the dependency.

```
lifecycle_state = cancelled | archived | hard_deleted  → 403 (offboarding)
lifecycle_state = read_only:
    method in {GET, HEAD, OPTIONS}                      → allow
    else                                               → 403 "tenant read-only (offboarding)"
lifecycle_state = active                               → fall through to today's
                                                          subscription_status gate (unchanged)
```

Two new fixed gate-contract lines join the existing 402/403 semantics; the
403 offboarding responses carry a distinct `detail` so the portal can render
the right screen. `get_platform_session` remains ungated (operators manage
tenants in any state).

## HTTP surface (`app/platform_/tenants/api.py`, all `CurrentSuperuser`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/platform/tenants/{id}/cancel` | MC submit (`tenant.cancel`, q=2) | begin offboarding |
| POST | `/platform/tenants/{id}/restore` | direct | reverse to active (while schema exists) |
| POST | `/platform/tenants/{id}/extend-retention` | direct | set `retention_hold_until` (legal hold) |
| GET | `/platform/tenants/{id}/lifecycle` | read | `tenant_lifecycle_events` timeline |

`TenantOut` gains `lifecycle_state` + the archival telemetry fields (read-only)
so the portal can render offboarding state and the archived list.

**Cut:** no `GET /{id}/archive` signed-URL endpoint (app has no S3 creds).
Retrieval of an archive is an operator runbook procedure keyed off
`archive_storage_key`.

## Infra-side archival (`infra/offboarding/`, mirrors `infra/backups/`)

A host-side script (systemd timer) polls for tenants where
`lifecycle_state = 'archived' AND archive_checksum IS NULL` — the "ready"
signal, exactly like Phase 4's `poll-verify-requests.sh`. For each:

```
pg_dump --schema="<schema_name>" <db>     # single-tenant logical dump
  | age -r <recipient>                    # encrypt (same cipher family as backups)
  | s3 upload → <bucket>/offboarding/<schema>-<ts>.sql.age
psql -c 'DROP SCHEMA "<schema_name>" CASCADE'
UPDATE platform.tenants
   SET archive_storage_key=…, archive_size_bytes=…, archive_checksum=…
 WHERE id=…
```

A companion script handles `hard_deleted` archive-object deletion. Neither the
`pg_dump`/`psql` binaries, the S3 credentials, nor the encryption key enter the
app image — consistent with the Phase-4 backups contract. Production is a
credentials/endpoint swap + the systemd timers, not a code change.

## Notifications (Phase 3)

New event codes, tenant-admin recipients, published via
`NotificationService.publish()` in the same transaction as each transition:
`tenant_offboarding_cancelled`, `tenant_offboarding_read_only`,
`tenant_offboarding_archived`, `tenant_offboarding_restored`. Platform-schema
template seeds + one portal-catalog mirror row each (per Phase 3 contract O).
Notices only — no secrets/PII in context.

## Portal (contract-N scope exception for Phase 7)

- Tenant detail page: an **Offboarding** section — current `lifecycle_state`
  (`<StatusBadge>`), the lifecycle timeline, and actions: **Cancel** via
  `<MakerCheckerConfirmDialog>` (a wizard step captures reason + optional
  customer message), **Restore** and **Extend retention** via base
  `<ConfirmDialog>`.
- `/platform/tenants/archived` — a `<DataTable>` list of archived tenants with
  archive size / age / storage key.
- `@sacco/schemas` lifecycle types + `@sacco/api-client` resource additions +
  a `StatusBadge` mapping row for the new `tenant` lifecycle states.

## Observability (optional, light)

A committed Logfire alert for archival failures — the infra script can write a
failure marker or leave `archived` rows with `archive_checksum IS NULL` beyond
a threshold; alert on "tenant stuck in archived without a completed dump > 24h."
Deferred to the close-out increment; not load-bearing.

## Settings

| Setting | Default | Effect |
|---|---|---|
| `OFFBOARDING_READ_ONLY_DAYS` | 7 | `cancelled → read_only` delay |
| `OFFBOARDING_ARCHIVE_DAYS` | 83 | `read_only → archived` delay (90d total) |
| `OFFBOARDING_HARD_DELETE_DAYS` | 2555 | `archived → hard_deleted` delay (~7y) |

## Out of scope / cuts

- In-app archive download / signed URLs (no S3 creds in app) → runbook.
- `retention_policy` enum tiers → single global window + per-tenant hold.
- Restore after physical archival → runbook restore-from-archive, not API.
- No tenant-schema migration; no changes to member/tenant-user auth.

## Decomposition (4 increments, each its own sub-plan)

1. **Data + state machine** — migration 015 (`lifecycle_state`, telemetry
   columns, `tenant_lifecycle_events`), `OffboardingService` transitions +
   restore boundary + `SubscriptionService` coupling, unit tests. No HTTP/gate.
2. **Gate + API + notifications** — method-aware `read_only` gate, the 4
   endpoints, the `tenant.cancel` maker-checker executor, the 4 event codes +
   template seeds.
3. **Beat jobs + infra archival** — the 3 daily transition jobs
   (`app/platform_/tenants/beat.py` + celery registration) and
   `infra/offboarding/` (archive + delete scripts, systemd units) + telemetry
   write-back.
4. **Portal + docs close-out** — offboarding UI + archived list, `@sacco/*`
   additions, `docs/tenant-offboarding.md`, CLAUDE.md contracts section +
   roadmap row 7 → Done, optional archival-failure alert.

## Testing

- Unit: `OffboardingService` transitions (each state change writes the right
  event row + timestamps; restore boundary; hold blocks archival), with a
  frozen clock for the beat thresholds.
- Integration: the gate (read_only allows GET, 403s writes; cancelled/archived
  403 everything; active unchanged), the endpoints (auth gates, maker-checker
  submit for cancel, direct restore/extend, lifecycle timeline), notification
  publish per transition.
- Infra script: dry-run / MinIO-local exercise of the dump→encrypt→upload→drop
  path against a throwaway schema (mirrors Phase 4's restore-drill test).
- Gates: ruff + mypy (strict) clean; `env -u DATABASE_URL pytest` for the
  Python suites; portal `pnpm --filter @sacco/portal test|lint|typecheck`.
