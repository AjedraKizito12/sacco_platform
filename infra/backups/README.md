# Backups & Disaster Recovery (Phase 4)

PostgreSQL WAL archiving + base backups via **pgBackRest** into a
**MinIO** (S3-compatible) bucket, with an automated **restore-verify drill**.
The whole pipeline runs locally in Docker Compose; moving to production is a
credential/endpoint swap in `pgbackrest.conf` plus running the systemd units
in `systemd/` instead of the backup container's crontab.

## Components

| File | Role |
|------|------|
| `pgbackrest.conf` | Single pgBackRest config (repo = MinIO S3, stanza `sacco`, AES-256 repo encryption). The one file that changes for production. |
| `Dockerfile.postgres` | `postgres:16` + the `pgbackrest` binary (WAL `archive_command` runs inside the postgres container). |
| `Dockerfile.backup` | Backup sidecar: `pgbackrest` + `supercronic` + `psql` + `mc`. Runs base/verify/prune on cron plus a verify-request poll. |
| `crontab` | Sidecar schedules (base nightly, verify weekly, prune daily, poll every minute). |
| `scripts/*.sh` | `lib.sh` (psql status reporters), `backup.sh`, `restore-staging.sh` (the drill), `prune.sh`, `poll-verify-requests.sh`. |
| `systemd/*` | Production-host timers/services (documented, not exercised locally). |

Backup status is reported into `platform.backup_runs` /
`platform.backup_verifications` via psql; the app reads those tables through
`/platform/ops/backups` (superuser).

## Local bring-up

From the repo root (project name is pinned to `sacco-platform`):

```bash
# 1. Build the archiving postgres image and start the object store + db.
#    minio-certs generates the self-signed TLS cert MinIO serves; the
#    postgres image bundles the pgbackrest binary.
docker compose build postgres
docker compose up -d minio-certs minio minio-setup postgres
docker compose logs minio-setup | grep minio-setup-done

# 2. One-time: create the pgBackRest stanza (safe to re-run). pgBackRest
#    refuses to run as root, so exec as the postgres OS user.
docker compose exec -T -u postgres postgres \
  pgbackrest --stanza=sacco --config=/etc/pgbackrest/pgbackrest.conf stanza-create

# 3. Confirm the repo + archiving are wired end-to-end
docker compose exec -T -u postgres postgres \
  pgbackrest --stanza=sacco --config=/etc/pgbackrest/pgbackrest.conf check

# 4. Start the backup sidecar (cron + verify-request poll)
docker compose up -d backup

# 5. Take a base backup on demand (as the postgres user)
docker compose exec -T -u postgres backup pgbackrest \
  --stanza=sacco --config=/etc/pgbackrest/pgbackrest.conf backup --type=full
```

> MinIO serves a self-signed cert locally, so `mc` calls against it use
> `--insecure` and pgBackRest sets `repo1-storage-verify-tls=n`. Both are
> local-only; production points at a real CA (see the swap checklist below).

## Running a restore-verify drill

On demand, either trigger it through the portal
(`/platform/operations/backups` → "Verify now") — which inserts a
`requested` row that the sidecar's minute poll picks up — or run the script
directly inside the sidecar:

```bash
docker compose exec -T backup /opt/backups/scripts/restore-staging.sh
```

The drill restores the latest base + WAL into a throwaway Postgres, runs smoke
queries (`platform.tenants` count > 0 and a known tenant row count), records
PASS/FAIL + duration into `platform.backup_verifications`, and tears the
throwaway cluster down unconditionally.

## Production swap (checklist)

Everything below is a config/secrets change — **no code changes**:

1. `pgbackrest.conf`:
   - `repo1-s3-endpoint` → the real S3/GCS/B2 endpoint.
   - `repo1-s3-uri-style=host` for AWS S3 (keep `path` for MinIO).
   - `repo1-s3-key` / `repo1-s3-key-secret` → injected from the secrets manager.
   - `repo1-cipher-pass` → a real key from the secrets manager (**never** the
     `local-dev-cipher-change-in-prod` default). Custody + rotation for this
     key is a runbook TODO (see `docs/runbooks/backup-verification.md`).
2. Run the `systemd/pgbackrest-backup.timer` and
   `systemd/pgbackrest-verify.timer` on the production DB host instead of the
   backup container's crontab.
3. Ensure the bucket is private with server-side encryption and a policy that
   denies public access.

## Notes

- `archive_command` failing before `stanza-create` runs is expected on first
  boot; Postgres still starts. The command starts succeeding once the stanza
  exists.
- pgBackRest connects to the cluster as `sacco` (the `POSTGRES_USER`
  superuser), set via `pg1-user` in `pgbackrest.conf` — the default image has
  no `postgres` role.
