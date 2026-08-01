# Runbook: Backup verification (the restore-verify drill)

A backup you have never restored is a hope, not a backup. Phase 4 runs an
automated **restore-verify drill** that proves the pgBackRest repo is actually
restorable, on a schedule and on demand, and records the outcome where operators
can see it.

## What the drill does

`infra/backups/scripts/restore-staging.sh`:

1. Spins up a throwaway Postgres container from the archiving image.
2. Restores the **latest** base backup + WAL into it (as the `postgres` user).
3. Starts it, letting Postgres complete archive recovery and auto-promote.
4. Smoke-queries it: the hard invariant is
   `platform.platform_users >= 1` (migration 002 always seeds the bootstrap
   superuser, so a faithfully restored `platform` schema has at least that row).
   The tenant count is reported in the detail, not asserted — a fresh platform
   can legitimately have zero tenants.
5. Records `passed` / `failed` plus a `platform_users=… tenants=…` detail (and
   `started_at` / `finished_at`, i.e. the restore time) into
   `platform.backup_verifications`, then tears the throwaway cluster down
   unconditionally.

It touches **no live data** — everything happens in the disposable container.

## When it runs

- **Weekly**, Sunday 03:00, via cron in the backup sidecar (local) or the
  `pgbackrest-verify.timer` systemd unit (production).
- **On demand**, two ways that converge on the same script:
  - An operator clicks **Verify now** in the portal
    (`/platform/operations/backups`), which inserts a `requested` row that the
    sidecar's minute poll (`poll-verify-requests.sh`) claims and runs.
  - Directly: `docker compose exec -T backup /opt/backups/scripts/restore-staging.sh`.

## Reading the portal widget

`/platform/operations/backups` (platform **superuser**) shows:

- **Two freshness tiles.** A tile turns red ("stale") when the underlying
  timestamp is missing or too old:
  - *Last successful backup* — stale after **24h** (`BACKUP_STALE_HOURS`).
  - *Last verified restore* — stale after **7 days** (`VERIFY_STALE_DAYS`).
  A green tile means the last event is within the threshold.
- **Repository size trend** — base backup repo size across recent runs (a sudden
  drop or spike is worth investigating).
- **Recent backup runs** — a table with type, status badge, repo size, and
  duration.

## What to do on a `failed` verification (or a stale tile)

A red *Last verified restore* tile or a `failed` row means the repo could not be
restored — treat it as a **P1**: your backups may be unusable.

1. **Read the detail.** The `detail` column on the failed
   `platform.backup_verifications` row names the failing step ("pgbackrest
   restore failed", "restored cluster did not start", "platform.platform_users
   empty after restore", …).
2. **Reproduce with logs.** Run the drill manually and read the full output:
   ```bash
   docker compose exec -T backup /opt/backups/scripts/restore-staging.sh
   ```
3. **Check the repo itself.**
   ```bash
   docker compose exec -T -u postgres postgres \
     pgbackrest --stanza=sacco --config=/etc/pgbackrest/pgbackrest.conf info
   ```
   `status: ok` with recent backups is healthy. `status: error (no valid
   backups)` or a stale `wal archive max` points at broken archiving or a repo
   that never received a base backup.
4. **Common causes:** object-store credentials rotated but not updated
   (`PGBACKREST_REPO1_*`), a wrong or missing `repo1-cipher-pass` (repo reads as
   corrupt), WAL archiving stopped (`archive_command` failing on the primary), or
   the object store unreachable / full.
5. **If a real restore is needed**, proceed to
   [`restore-from-pitr.md`](./restore-from-pitr.md) (whole cluster) or
   [`single-tenant-recovery.md`](./single-tenant-recovery.md) (one tenant).

A red *Last successful backup* tile with a healthy verify usually means the
nightly base backup did not run — check the sidecar / `pgbackrest-backup.timer`
and the primary's `archive_command`.
