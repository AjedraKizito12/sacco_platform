#!/usr/bin/env bash
# Shared helpers for the tenant-offboarding archival pipeline.
#
# Mirrors infra/backups/lib.sh. Two responsibilities:
#   1. Read the app-written "ready" signal and write archival telemetry back
#      into platform.tenants via psql. The app (OffboardingService + the daily
#      beat) is the ONLY writer of lifecycle_state; this pipeline only fills the
#      archive_* columns and DROPs the physical schema.
#   2. Run pg_dump inside the postgres container as the `postgres` user (the DB
#      client tools live there, not on the sidecar/host), then encrypt (age) and
#      upload (aws s3) the dump from the sidecar/host.
#
# Secrets (S3 creds, the age recipient) come from the HOST env only — never the
# app image. Local dev points aws at MinIO; production swaps the endpoint/creds
# via the systemd EnvironmentFile (/etc/sacco/offboarding.env).
set -euo pipefail

: "${PGHOST:=postgres}"
: "${PGUSER:=sacco}"
: "${PGDATABASE:=sacco}"
export PGPASSWORD="${PGPASSWORD:-sacco}"
: "${COMPOSE_PROJECT:=sacco-platform}"

# Object store. Local dev = MinIO; production overrides all four.
: "${OFFBOARDING_BUCKET:=sacco-offboarding}"
: "${AWS_S3_ENDPOINT:=http://minio:9000}"
: "${AGE_RECIPIENT:?AGE_RECIPIENT (age public key) must be set}"

# Resolve the running postgres container id for this compose project.
postgres_container() {
  docker ps -q \
    --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}" \
    --filter "label=com.docker.compose.service=postgres" | head -n1
}

# psql against the platform schema (client runs on the sidecar/DB host).
psql_platform() {
  psql -v ON_ERROR_STOP=1 -qtA -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" \
    -c "SET search_path TO platform; $1"
}

# Tenants the app has flagged ready for physical archival.
# Prints tab-separated: <tenant_id>\t<schema_name>
list_archive_ready() {
  psql_platform "SELECT id, schema_name FROM tenants
    WHERE lifecycle_state='archived' AND archive_checksum IS NULL;"
}

# Hard-deleted tenants whose encrypted archive object should be purged.
# Prints tab-separated: <tenant_id>\t<archive_storage_key>
list_hard_deleted_with_archive() {
  psql_platform "SELECT id, archive_storage_key FROM tenants
    WHERE lifecycle_state='hard_deleted' AND archive_storage_key IS NOT NULL;"
}

# Write archival telemetry back after a successful dump+upload+drop.
record_archive() { # id storage_key size_bytes checksum
  psql_platform "UPDATE tenants SET
    archive_storage_key=\$\$${2}\$\$,
    archive_size_bytes=${3},
    archive_checksum=\$\$${4}\$\$
    WHERE id='${1}';"
}

# Null the archive key once the object is deleted for a hard_deleted tenant.
clear_archive_key() { # id
  psql_platform "UPDATE tenants SET archive_storage_key=NULL WHERE id='${1}';"
}

# pg_dump a single schema, as the postgres user, inside the postgres container.
# Streams SQL to stdout.
pg_dump_schema() { # schema
  local c
  c="$(postgres_container)"
  if [ -z "$c" ]; then
    echo "pg_dump_schema: postgres container not found for ${COMPOSE_PROJECT}" >&2
    return 1
  fi
  docker exec -u postgres "$c" pg_dump -d "$PGDATABASE" --schema="$1" --no-owner
}

# Drop a physical schema after its dump is safely uploaded.
drop_schema() { # schema
  psql_platform "DROP SCHEMA IF EXISTS \"${1}\" CASCADE;"
}

# aws s3 wrapper honoring the MinIO/prod endpoint.
s3() { aws --endpoint-url "$AWS_S3_ENDPOINT" s3 "$@"; }
