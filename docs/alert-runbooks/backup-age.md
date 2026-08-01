# Alert: Backup age exceeded

Definition: `infra/observability/logfire/alerts/backup-age.json`

- **Severity:** critical
- **Trigger condition:** `sacco_backup_age_seconds` exceeds 36 hours
  (129600s) on its latest reading.

## Likely causes

- The pgBackRest sidecar / systemd timer stopped running (crashed,
  disabled, or the host is down) — see `infra/backups/`.
- A backup job ran but failed (check `platform.backup_runs.status` for
  recent `failed` rows rather than a missing row).
- Credential/endpoint rotation broke the S3/cipher configuration
  (`pgbackrest.conf`) without anyone updating the app's telemetry.
- No succeeded backup run has EVER completed (the gauge reports the
  ~1-year `NO_BACKUP_AGE_SENTINEL` in this case) — this is the "day one,
  nothing configured yet" case as much as an outage.

## Response steps

1. Query `platform.backup_runs` directly (ordered by `finished_at DESC`)
   to see the actual recent run history and any `failed`/`error` rows —
   this is faster than only trusting the gauge.
2. Check the backup sidecar/systemd timer status on the DB host:
   `systemctl status` the relevant unit(s) documented in
   `infra/backups/systemd/`.
3. Check pgBackRest logs for the most recent attempt (auth failures,
   network errors to the S3/MinIO endpoint, disk space on the WAL archive
   path).
4. If credentials/endpoint recently rotated, verify `pgbackrest.conf`
   matches the current secret.
5. Once the underlying issue is fixed, trigger a manual backup run per the
   Phase 4 runbooks (`docs/runbooks/`) and confirm `platform.backup_runs`
   gets a fresh `succeeded` row — the gauge will self-clear on the next
   beat tick once the DB reflects it.
6. Follow up with the operator-triggered verification
   (`POST /platform/ops/backups/trigger-verification`, superuser) once a
   fresh backup exists, to confirm restorability — see the Ops module
   contracts in CLAUDE.md.

## Escalation

- This alert gates production launch (Phase 4 dependency). Treat > 36h
  with no successful backup as a **P1**: the platform has no recent
  recovery point. Page on-call immediately; do not wait for the next
  scheduled backup window to "fix itself."
