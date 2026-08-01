# Runbook: Full-cluster restore (Point-in-Time Recovery)

**When to use:** the primary Postgres is lost or corrupted and you need to bring
the whole cluster back to a specific moment (e.g. just before a bad migration or
a destructive bulk operation). This restores **every** schema — `platform` and
all `tenant_*` — as of the target time.

> This is a destructive, whole-cluster operation. For recovering a single tenant
> without rolling everyone back, use [`single-tenant-recovery.md`](./single-tenant-recovery.md).

## Preconditions

- The pgBackRest repo (MinIO locally, the real object store in prod) is reachable
  and holds a base backup at or before the target time, plus the WAL that follows
  it. Confirm with `pgbackrest --stanza=sacco info`.
- You have the repo secrets (`PGBACKREST_REPO1_S3_KEY`, `..._S3_KEY_SECRET`,
  `..._CIPHER_PASS`). Without the cipher pass the repo is unreadable.
- Decide the recovery target timestamp (UTC), e.g. `2026-08-01 11:10:00+00`.

## Local / Docker Compose procedure

1. **Stop everything that writes.** The app must not talk to the DB during a
   restore.
   ```bash
   docker compose stop api worker beat
   ```

2. **Stop Postgres and clear the data dir** (pgBackRest restores into an empty
   `$PGDATA`; run as the `postgres` user — it refuses to run as root).
   ```bash
   docker compose stop postgres
   docker compose run --rm --no-deps --entrypoint bash -u postgres postgres -lc \
     "find /var/lib/postgresql/data -mindepth 1 -delete"
   ```

3. **Restore to the target time.**
   ```bash
   docker compose run --rm --no-deps --entrypoint bash -u postgres postgres -lc \
     "pgbackrest --stanza=sacco --config=/etc/pgbackrest/pgbackrest.conf \
        --type=time --target='2026-08-01 11:10:00+00' --delta restore"
   ```
   pgBackRest writes `recovery.signal` + a `restore_command` into
   `postgresql.auto.conf`; on start Postgres replays WAL up to the target and
   then promotes.

4. **Start Postgres and let recovery finish.**
   ```bash
   docker compose up -d postgres
   docker compose logs -f postgres   # wait for "archive recovery complete"
                                      # then "database system is ready to accept connections"
   ```

5. **Verify before re-opening the app.**
   ```bash
   docker compose exec -T postgres psql -U sacco -d sacco -c \
     "SELECT count(*) FROM platform.platform_users;"      # >= 1 (bootstrap superuser)
   docker compose exec -T postgres psql -U sacco -d sacco -c \
     "SELECT version_num FROM platform.alembic_version;"  # expected schema head
   ```

6. **Re-open the app.**
   ```bash
   docker compose up -d api worker beat
   ```

## Production notes

- **Endpoint / secrets:** production points `repo1-s3-endpoint` at the real
  object store and injects the `PGBACKREST_REPO1_*` secrets from the secrets
  manager (never the `local-dev-cipher-change-in-prod` default). Drop
  `repo1-storage-verify-tls=n` and set `repo1-storage-ca-file` for a real CA.
  See `infra/backups/README.md` → "Production swap".
- **Where it runs:** in production pgBackRest runs on the DB host (not via the
  Docker socket). The commands are the same minus the `docker compose run`
  wrapper — run them directly as the `postgres` user on the host.
- **`--type=time` vs other targets:** use `--type=default` to recover to the end
  of the archived WAL (latest possible), `--type=immediate` to stop as soon as
  the backup is consistent (fastest, least data), or `--set=<label>` to restore a
  specific base backup. `info` lists the available backup labels.
- **RTO:** the weekly verify drill restores this same repo end-to-end in well
  under a minute on the current dataset (see `docs/runbooks/drills/`). A real
  cluster's RTO scales with database size and WAL volume.
