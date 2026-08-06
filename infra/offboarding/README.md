# Tenant Offboarding — Physical Archival (Phase 7)

Infra-side pipeline that turns a **logically** offboarded tenant into a
**physically** archived one: `pg_dump` the tenant schema → **age**-encrypt →
upload to object storage (**MinIO** locally, S3 in prod) → `DROP SCHEMA CASCADE`
→ write archival telemetry back into `platform.tenants`.

The application owns the lifecycle state machine (`OffboardingService` + the
daily transition beat). This pipeline is a **downstream consumer of the app's
"ready" signal** and the ONLY code that touches the physical schema or fills the
`archive_*` telemetry columns. No `pg_dump`, `age`, S3 client, or `DROP SCHEMA`
lives in the app image (mirrors the Phase-4 backups contract).

## The app ↔ infra handshake

| Column (`platform.tenants`) | Written by | Meaning |
|---|---|---|
| `lifecycle_state='archived'`, `archive_checksum IS NULL` | app (beat) | **ready** — dump me |
| `archive_storage_key`, `archive_size_bytes`, `archive_checksum` | this pipeline | archived; schema dropped |
| `lifecycle_state='hard_deleted'`, `archive_storage_key` set | app (beat) | **ready** — purge my object |
| `archive_storage_key = NULL` (after purge) | this pipeline | object removed |

`archive_checksum IS NULL` is the "not yet dumped" flag: once set, the app's
`OffboardingService.restore()` refuses to restore (the schema is gone). Restoring
a physically archived tenant is a manual runbook procedure (retrieve the object
by `archive_storage_key`, decrypt with the age private key, `psql` it into a new
schema), not an API surface.

## Components

| File | Role |
|------|------|
| `lib.sh` | Shared helpers: the ready-signal queries, telemetry write-back, `pg_dump_schema` (execs into the postgres container as the `postgres` user), `drop_schema`, and the `s3`/endpoint wrapper. |
| `archive.sh` | For each ready tenant: dump → age-encrypt → upload → `DROP SCHEMA` → `record_archive`. Uploads **before** dropping. |
| `delete-archive.sh` | For each `hard_deleted` tenant with an archive object: delete the object → null the key. |
| `systemd/*` | Production-host timers/services: archive nightly **03:00 UTC** (one hour after the 02:00 base backup, to avoid contention), purge weekly (Sun 04:00). |

## Environment (host-only secrets)

Set via the systemd `EnvironmentFile` (`/etc/sacco/offboarding.env`) in prod, or
your shell locally. `AGE_RECIPIENT` is **required** — the scripts refuse to run
without it.

```sh
AGE_RECIPIENT=age1...            # age PUBLIC key; the private key never lives here
OFFBOARDING_BUCKET=sacco-offboarding
AWS_S3_ENDPOINT=http://minio:9000  # prod: drop this to use real S3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
PGHOST=postgres PGUSER=sacco PGDATABASE=sacco PGPASSWORD=...
COMPOSE_PROJECT=sacco-platform
```

age encrypts to a **public** recipient key; decryption needs the paired private
key, which is deliberately kept out of this host — archives are write-only here.

## Production vs local

Local dev drives the host Docker daemon and points `aws` at MinIO. Production is
a credential/endpoint swap (real S3 + the prod age recipient) plus enabling the
systemd timers instead of a cron entry — no code change, matching the Phase-4
backups model. `age` must be present on the DB host / in the sidecar image; the
backups image does not bundle it, so add it where these scripts run.

## Drill (manual)

Because `pg_dump`/`age`/`psql` live in the containers (not the host), the drill
runs against a throwaway schema, mirroring `infra/backups/restore-staging.sh`:

```bash
# 1. Create a throwaway schema + a fake "ready" tenant row pointing at it.
docker exec sacco-platform-postgres-1 psql -U sacco -d sacco -c \
  "CREATE SCHEMA tenant_drill; CREATE TABLE tenant_drill.canary(x int); \
   INSERT INTO tenant_drill.canary VALUES (1);"
docker exec sacco-platform-postgres-1 psql -U sacco -d sacco -c \
  "INSERT INTO platform.tenants (id, slug, schema_name, name, status, is_active, \
     subscription_status, seed_version, lifecycle_state, archived_at, \
     created_at, updated_at) \
   VALUES (gen_random_uuid(), 'drill', 'tenant_drill', 'Drill', 'active', true, \
     'pending', 1, 'archived', now(), now(), now());"

# 2. Run the pipeline (needs age + aws + the env above on the host).
AGE_RECIPIENT=age1... ./archive.sh

# 3. Assert: object uploaded, telemetry filled, schema gone.
docker exec sacco-platform-postgres-1 psql -U sacco -d sacco -c \
  "SELECT lifecycle_state, archive_storage_key, archive_size_bytes, archive_checksum \
     FROM platform.tenants WHERE slug='drill';"
docker exec sacco-platform-postgres-1 psql -U sacco -d sacco -c \
  "SELECT 1 FROM information_schema.schemata WHERE schema_name='tenant_drill';"  # 0 rows
```
