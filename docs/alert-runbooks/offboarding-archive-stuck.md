# Alert: Tenant offboarding archive stuck

Definition: `infra/observability/logfire/alerts/offboarding-archive-stuck.json`

- **Severity:** warning
- **Source:** **unavailable** (staged placeholder — no metric emits this
  signal yet; see the alert `notes`).
- **Trigger condition (once instrumented):** one or more
  `platform.tenants` rows with `lifecycle_state='archived'` and
  `archive_checksum IS NULL` older than 24h — i.e. the app flagged them
  ready for physical archival but the infra-side pipeline never dumped
  them.

## Why this matters

Phase 7 splits offboarding into an **app** half (the lifecycle state
machine + daily beat, which sets `lifecycle_state='archived'`) and an
**infra** half (`infra/offboarding/archive.sh`, which pg_dumps the schema,
encrypts, uploads, drops the schema, and fills `archive_checksum`). If the
infra job stops running, tenants sit in `archived` with the schema still
present and no encrypted archive object — a silent failure with no in-app
signal. This alert (once real) surfaces that gap.

## Response steps

1. Confirm the backlog directly:
   ```sql
   SELECT id, slug, schema_name, archived_at
   FROM platform.tenants
   WHERE lifecycle_state = 'archived' AND archive_checksum IS NULL
   ORDER BY archived_at;
   ```
2. Check the archival timer/service on the DB host:
   `systemctl status offboarding-archive.timer offboarding-archive.service`
   (units in `infra/offboarding/systemd/`).
3. Check the last `offboarding-archive.service` run's journal for the
   common failure modes: missing `AGE_RECIPIENT`, bad/rotated S3
   credentials, the MinIO/S3 endpoint unreachable, or the postgres
   container not found (the script execs `pg_dump` inside it).
4. Verify `age` and `aws` are present on the host / in the sidecar image —
   the backups image does not bundle `age`.
5. Once fixed, run `infra/offboarding/archive.sh` manually and confirm the
   backlog query returns zero rows and each affected tenant now has
   `archive_storage_key` / `archive_size_bytes` / `archive_checksum` set
   and its `tenant_<slug>` schema dropped.

## Making the alert real

This is staged `unavailable` because nothing emits the backlog count. To
promote it: add a `sacco_offboarding_archive_pending` gauge on the
observability beat (a query against `platform.tenants`) per the Phase 5
metrics pattern, or add a `systemd` `OnFailure=` hook on
`offboarding-archive.service` that posts to Logfire. Then flip `source` to
`metric` and write the query.
