#!/usr/bin/env bash
# Restore the latest backup into a throwaway postgres, smoke-test it, and record
# the result in platform.backup_verifications.
#
# Runs inside the backup sidecar, driving the HOST Docker daemon over the mounted
# socket. Two consequences of that:
#   * docker run/exec target the host — we cannot bind-mount the sidecar's own
#     /etc/pgbackrest/pgbackrest.conf into the staging container (that path only
#     exists inside the sidecar), so we `docker cp` the config in after start.
#   * pgBackRest refuses to run as root, so restore/start run as `-u postgres`.
# Secrets are the local-dev MinIO values; production injects PGBACKREST_REPO1_*
# from the secrets manager and runs this drill on a dedicated restore host
# (see the systemd units, Task 7).
#
# Arg $1 (optional) = a backup_verifications.id to update (the poller passes the
# claimed request id; a scheduled cron run passes nothing and we insert our own).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib.sh"

VERIFY_ID="${1:-}"
if [ -z "$VERIFY_ID" ]; then
  VERIFY_ID="$(insert_scheduled_verification)"
  claim_verification "$VERIFY_ID"
fi

STAGING="sacco-restore-staging-$$"
NET="${COMPOSE_PROJECT:-sacco-platform}_sacco_net"
PGDATA_DIR="/var/lib/postgresql/data"

cleanup() { docker rm -f "$STAGING" >/dev/null 2>&1 || true; }
trap cleanup EXIT

fail() { finish_verification "$VERIFY_ID" failed "$1"; echo "DRILL FAIL: $1" >&2; exit 1; }

# 1. Ephemeral container from the archiving postgres image. Override the
#    entrypoint so the base image does NOT initialise a fresh cluster — we
#    restore into an empty data dir instead.
docker run -d --name "$STAGING" --network "$NET" \
  --entrypoint bash \
  -e PGBACKREST_REPO1_S3_KEY=sacco-minio \
  -e PGBACKREST_REPO1_S3_KEY_SECRET=sacco-minio-secret \
  -e PGBACKREST_REPO1_CIPHER_PASS=local-dev-cipher-change-in-prod \
  -e PGPASSWORD=sacco \
  sacco-platform-postgres -c "sleep infinity" >/dev/null \
  || fail "could not start staging container"

# 2. Copy the pgBackRest config in, then restore the latest backup into a clean
#    data dir as the postgres user.
docker exec "$STAGING" mkdir -p /etc/pgbackrest || fail "could not mkdir /etc/pgbackrest"
docker cp /etc/pgbackrest/pgbackrest.conf "$STAGING:/etc/pgbackrest/pgbackrest.conf" \
  || fail "could not copy pgbackrest config into staging"
docker exec -u postgres "$STAGING" bash -lc \
  "find '$PGDATA_DIR' -mindepth 1 -delete && chmod 700 '$PGDATA_DIR' && \
   pgbackrest --stanza=sacco --config=/etc/pgbackrest/pgbackrest.conf --delta restore" \
  || fail "pgbackrest restore failed"

# 3. Start the restored cluster (archive recovery → auto-promote) and smoke it:
#    the cluster must open AND known rows must be present. The hard invariant is
#    platform.platform_users >= 1 — migration 002 seeds the bootstrap superuser,
#    so a faithfully restored platform schema always has at least that row (a
#    fresh platform can have zero tenants, so tenants is reported, not asserted).
docker exec -u postgres "$STAGING" \
  pg_ctl -D "$PGDATA_DIR" -w -t 120 start || fail "restored cluster did not start"

USERS="$(docker exec "$STAGING" psql -U sacco -d sacco -tAqc \
  'SELECT count(*) FROM platform.platform_users;')" || fail "platform.platform_users query failed"
[ "${USERS:-0}" -ge 1 ] || fail "platform.platform_users empty after restore"
TENANTS="$(docker exec "$STAGING" psql -U sacco -d sacco -tAqc \
  'SELECT count(*) FROM platform.tenants;' 2>/dev/null || echo 0)"

finish_verification "$VERIFY_ID" passed "platform_users=$USERS tenants=$TENANTS"
echo "DRILL PASS: platform_users=$USERS tenants=$TENANTS"
