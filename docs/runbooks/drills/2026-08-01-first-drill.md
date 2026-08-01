# First restore-verify drill — 2026-08-01

**Result: PASS.** The pgBackRest repo restored cleanly into a throwaway Postgres,
completed archive recovery, promoted, and passed the smoke invariant. This is the
Phase 4 roadmap's required proof that the backup pipeline is restorable end to end.

## Environment

Local Docker Compose stack (`sacco-platform`): archiving `postgres:16` +
pgBackRest → MinIO (S3), AES-256 repo encryption, stanza `sacco`. Restore driven
by `infra/backups/scripts/restore-staging.sh` into an ephemeral container.

## Metrics

| Metric | Value |
|--------|-------|
| Verification result | `passed` |
| **RTO (restore → smoke pass)** | **34.2 s** (`finished_at − started_at`) |
| Smoke invariant | `platform.platform_users = 1` (≥ 1 required) → OK |
| Tenants restored (reported) | `0` (fresh platform schema — see note) |
| Base backup | full, database size 57 MB, repo (compressed, encrypted) 6.5 MB |
| Base backup duration | ~36 s |
| Repo status | `ok` — 2 full backups retained, WAL archive continuous |

## Captured output

Drill:
```
DRILL PASS: platform_users=1 tenants=0
```

Verification row (`platform.backup_verifications`, latest):
```
 status |           detail           |    duration
--------+----------------------------+-----------------
 passed | platform_users=1 tenants=0 | 00:00:34.199814
```

`pgbackrest info` (repo summary):
```
stanza: sacco
    status: ok
    cipher: aes-256-cbc
    db (current)
        wal archive min/max (16): 00000001000000000000002B / 000000010000000000000035
        full backup: 20260801-111540F
            database size: 57MB, database backup size: 57MB
            repo1: backup set size: 6.5MB, backup size: 6.5MB
```

## Notes

- **`tenants=0` is expected, not a failure.** This dev cluster's `platform`
  schema was freshly migrated during the Phase 4 build (migrations reseed only
  the bootstrap superuser), so `platform.tenants` is genuinely empty. The drill
  asserts on `platform.platform_users` precisely because it is always ≥ 1 after a
  faithful restore; the tenant count is reported for visibility only. See
  [`../backup-verification.md`](../backup-verification.md).
- **RTO caveat.** 34 s reflects a 57 MB database with a handful of WAL segments.
  Real-world RTO scales with database size and the volume of WAL to replay from
  the base backup to the recovery target; re-baseline this figure against
  production-scale data before quoting an SLA.
- **On-demand path also exercised.** Separately verified that inserting a
  `requested` row into `platform.backup_verifications` (what the portal's
  "Verify now" button does) is picked up by `poll-verify-requests.sh` and driven
  through `requested → running → passed`.

## How to reproduce

```bash
docker compose exec -T backup /opt/backups/scripts/restore-staging.sh | tee /tmp/drill.txt
docker compose exec -T postgres psql -U sacco -d sacco -c \
  "SELECT status, detail, finished_at-started_at AS duration \
     FROM platform.backup_verifications ORDER BY created_at DESC LIMIT 1;"
```
