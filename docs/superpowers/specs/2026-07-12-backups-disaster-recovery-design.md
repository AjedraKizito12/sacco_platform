# Phase 4 — Backups & Disaster Recovery (Design)

**Status:** Approved (brainstorming, 2026-07-12)
**Roadmap:** `docs/superpowers/plans/saas-launch-roadmap.md` §Phase 4
**Register:** infrastructure + a thin platform API/portal surface. Backend and infra work; not a bounded context.

## Goal

Establish provable, regularly-tested PostgreSQL backup and restore for the
SACCO platform, with the whole pipeline runnable and **tested end-to-end in
local Docker Compose**. Losing a tenant's ledger is existential; the roadmap's
first-order risk is that untested backups silently fail, so the design's
centerpiece is the automated verify drill, not the backup itself.

Targets (roadmap): **RPO 5 minutes** (WAL archiving), **RTO 2 hours** (restore
from latest base + WAL).

## Deployment strategy: local-complete via MinIO

The platform currently runs only in Docker Compose (no production host). Rather
than write configs that can't be exercised, this phase runs the **full pipeline
locally** against a MinIO (S3-compatible) object store:

- pgBackRest archives WAL + takes base backups into a MinIO bucket.
- The verify drill restores into an ephemeral Postgres and smoke-tests it.
- Retention/prune runs on schedule.

Moving to production later is a **credential/endpoint swap** in one config file
(`pgbackrest.conf`) plus running the already-written systemd units instead of
the container's cron. No code or query changes. Real-cloud concerns (KMS
encryption key custody, bucket IAM policy) are captured as runbook TODOs, not
built now.

## Architecture

```
┌─────────────┐   archive_command    ┌──────────────┐
│  postgres   │─────────────────────▶│    MinIO     │
│ (archive_   │   nightly base       │  (S3 bucket  │
│  mode=on)   │─────────────────────▶│  sacco-      │
└─────────────┘                      │  backups)    │
       ▲                             └──────┬───────┘
       │ restore (drill)                    │
┌──────┴───────────────┐   reads/writes     │
│  backup sidecar      │────────────────────┘
│  pgBackRest + cron   │
│  - full (nightly)    │   reports run/verify status via psql
│  - verify (weekly)   │──────────────────────┐
│  - prune (daily)     │                      ▼
│  - poll verify reqs  │            ┌──────────────────────┐
└──────────────────────┘            │ platform.backup_runs │
                                    │ platform.backup_     │
┌──────────────────────┐  reads     │   verifications      │
│ /platform/ops/backups│◀───────────└──────────────────────┘
│ (API, CurrentSuperuser)            ▲ trigger inserts a
└──────────┬───────────┘             │ 'requested' row
           │ portal                  │
┌──────────▼───────────┐             │
│ /platform/operations/│─────────────┘
│  backups (widget)    │
└──────────────────────┘
```

### Component 1: Infrastructure (`infra/backups/` + docker-compose)

- **`minio` service** — S3-compatible object store. A one-shot bootstrap job
  (mc) creates the versioned `sacco-backups` bucket and the pgBackRest access
  credentials. Data on a named volume.
- **Postgres changes** — `archive_mode=on`, `archive_command` calling
  `pgbackrest archive-push`, `wal_level=replica` (already default), and a
  `pgbackrest` role (replication + read). The `postgres` image is extended via
  a thin Dockerfile layer to include the pgBackRest binary (archive_command
  runs inside the postgres container). Applied through compose config, not by
  hand.
- **`backup` sidecar service** — pgBackRest + [supercronic] running:
  | Job | Schedule | Action |
  |-----|----------|--------|
  | base backup | nightly (02:00) | `pgbackrest backup --type=full` (weekly full, nightly incr in prod tuning; v1 keeps it simple with nightly full) |
  | verify drill | Sun 03:00 | `restore-staging.sh` |
  | prune | daily 04:00 | `pgbackrest expire` — 90-day retention, keep ≥6 weekly fulls |
  | verify-request poll | every 1 min | run drill if a `requested` verification row exists |
  WAL archiving is continuous (driven by postgres `archive_command`, not cron).
- **`infra/backups/pgbackrest.conf`** — single config, MinIO endpoint +
  credentials from env. The one file that changes for production.
- **`infra/backups/systemd/`** — `pgbackrest-verify.{service,timer}` and a
  backup timer for the future production host. Written and documented; not
  exercised locally (the container's cron is the local driver).

### Component 2: Verify drill (`infra/backups/restore-staging.sh`)

The heart of the phase. On each run:
1. Start an ephemeral Postgres container (throwaway volume).
2. `pgbackrest restore` latest base + WAL into it.
3. Smoke queries: `SELECT count(*) FROM platform.tenants` (> 0), and a
   per-tenant row-count check against a known seeded schema
   (`tenant_demo_sacco.members`) to catch row-level corruption, not just "the
   cluster starts".
4. Record PASS/FAIL + duration into `platform.backup_verifications` (via psql
   against the *primary*, not the restored copy).
5. Tear down the ephemeral container + volume unconditionally (trap EXIT).

Runs weekly by cron and on demand (poll loop picks up `requested` rows).

### Component 3: Data model + ops API (`app/platform_/ops/`)

New module following the standard layout (`models.py`, `schemas.py`,
`service.py`, `api.py`), one Alembic **platform** migration.

**Tables (platform schema):**
- `backup_runs` — `id`, `backup_type` (full/incr), `started_at`, `finished_at`,
  `status` (running/succeeded/failed), `repo_size_bytes` (nullable),
  `wal_lag_seconds` (nullable), `detail` (text, nullable), `created_at`.
- `backup_verifications` — `id`, `requested_by` (nullable UUID; null =
  scheduled), `status` (requested/running/passed/failed), `detail` (text,
  nullable), `started_at` (nullable), `finished_at` (nullable), `created_at`.

Scripts write to both via psql from the backup container (no app dependency on
pgBackRest).

**Endpoints — all `CurrentSuperuser`, direct action (no maker-checker):**
- `GET /platform/ops/backups` — recent `backup_runs` (default last 20) + the
  latest verification, as `BackupStatusOut`.
- `GET /platform/ops/backups/last-verified-at` — timestamp of the most recent
  `passed` verification (nullable).
- `POST /platform/ops/backups/trigger-verification` — inserts a `requested`
  `backup_verifications` row; **409** if one is already `requested` or
  `running` (no queue stacking). Returns the row.

`OpsService` is the only writer of these tables from the app side. Backend
tests use the established platform-session fixture pattern (see
`feedback_test_patterns`: `async_sessionmaker` + commit + cleanup, not
`flush()`).

### Component 4: Portal widget (`/platform/operations/backups`)

New page under the existing Operations nav group (superuser-gated in UX; API
enforces). Server component fetches initial status via the typed client;
client subcomponents mutate via TanStack Query.

- **Freshness tiles** — last successful backup (danger tint when >24h old),
  last verified restore (danger when >7d old). Uses `<RelativeTime>` /
  `<FormattedDateTime>`.
- **Repo size trend** — existing `@sacco/ui` `Chart` over
  `backup_runs.repo_size_bytes`.
- **Recent runs** — `<DataTable>` (contract T) over `backup_runs`, status via
  a new `backup_run` / `backup_verification` `<StatusBadge>` entity
  (status-maps row).
- **"Verify now"** — plain `<ConfirmDialog>` → trigger endpoint (direct admin
  action, not maker-checker), toast + refresh.

### Component 5: Runbooks + deliverables

- `docs/runbooks/restore-from-pitr.md` — full-cluster PITR restore.
- `docs/runbooks/single-tenant-recovery.md` — restore to ephemeral, `pg_dump`
  one schema, restore into the live primary.
- `docs/runbooks/backup-verification.md` — how the drill works, how to read the
  widget, what a failure means.
- `docs/runbooks/drills/2026-MM-DD.md` — the **first real drill report**,
  committed as proof the pipeline works.

## CLAUDE.md changes

This phase intentionally reaches outside the portal (contract N's portal-only
constraint applies to Phase 2/3 UI work, not infra). Document the sanctioned
scope:
- `docker-compose.yml` — minio, backup services, postgres archive config.
- new `infra/backups/` tree.
- `app/platform_/ops/` module + one platform migration.
- new `admin/apps/portal/app/platform/(authed)/operations/backups/` page.
- append an **Ops module contracts** subsection: `OpsService` is the only app
  writer of `backup_runs` / `backup_verifications`; the three endpoints are
  superuser-only; trigger-verification is idempotent-by-conflict (409 while one
  is pending); backup scripts are the source of truth and report via psql.

## Out of scope (v1)

- **Phase 5 metrics/alerting.** The tables record durations/sizes/lag; alerts
  (`sacco_backup_age_seconds` > threshold, paging) are Phase 5. The widget's
  freshness tiles are the only "alarm" surface for now.
- **KMS-managed encryption key + custody ceremony.** pgBackRest repo encryption
  is enabled with a config-supplied key locally; production key management is a
  runbook TODO, not built.
- **Arbitrary-timestamp PITR via API.** Point-in-time restore to a chosen
  timestamp is a runbook procedure, not a portal button.
- **Incremental/differential backup tuning.** v1 takes nightly fulls for
  simplicity; incr scheduling is a documented future optimization.
- **Multi-region repo replication.** Single bucket in v1.

## Testing strategy

- **Backend:** unit + integration tests for `OpsService` and the three
  endpoints (status read, last-verified-at with/without a passed row, trigger
  happy path, trigger 409 conflict), superuser gating. Real Postgres in Docker.
- **Infra (the real proof):** run the whole pipeline against a scratch stack —
  archive WAL, take a base backup, run `restore-staging.sh`, confirm it
  restores and the smoke queries pass, confirm a `backup_verifications` row
  lands as `passed`. Capture as the first drill report. Offline
  `alembic upgrade --sql` is known-broken repo-wide (migration 002 runs
  queries); smoke the migration against a scratch DB instead.
- **Portal:** vitest for the widget (tiles render freshness/danger states,
  "Verify now" calls trigger, empty state when no runs yet).

## Open decisions (resolved)

- Deploy target → **local-complete via MinIO** (production = credential swap).
- Ops status source → **platform tables**, written by scripts via psql
  (no pgBackRest binary or S3 client in the app image).
- Schedules/retention → **roadmap defaults** (nightly base, weekly verify,
  daily prune, 90-day / ≥6-weekly retention).
- Gating → **superuser**, direct action (no maker-checker).
