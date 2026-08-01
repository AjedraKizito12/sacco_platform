#!/usr/bin/env bash
# Shared helpers for the backup sidecar.
#
# Two responsibilities:
#   1. Run pgBackRest commands. pgBackRest needs the PostgreSQL data directory
#      and refuses to run as root, so we exec into the postgres container as
#      the `postgres` user (the sidecar has the Docker socket — a local-only
#      convenience; production runs pgBackRest on the DB host via systemd).
#   2. Report backup/verify status into the platform tables via psql.
set -euo pipefail

: "${PGHOST:=postgres}"
: "${PGUSER:=sacco}"
: "${PGDATABASE:=sacco}"
export PGPASSWORD="${PGPASSWORD:-sacco}"
: "${COMPOSE_PROJECT:=sacco-platform}"

PGBACKREST_ARGS=(--stanza=sacco --config=/etc/pgbackrest/pgbackrest.conf)

# Resolve the running postgres container id for this compose project.
postgres_container() {
  docker ps -q \
    --filter "label=com.docker.compose.project=${COMPOSE_PROJECT}" \
    --filter "label=com.docker.compose.service=postgres" | head -n1
}

# Run a pgBackRest command inside the postgres container as the postgres user.
pgbr() {
  local c
  c="$(postgres_container)"
  if [ -z "$c" ]; then
    echo "pgbr: postgres container not found for project ${COMPOSE_PROJECT}" >&2
    return 1
  fi
  docker exec -u postgres "$c" pgbackrest "${PGBACKREST_ARGS[@]}" "$@"
}

psql_platform() {
  psql -v ON_ERROR_STOP=1 -qtA -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" \
    -c "SET search_path TO platform; $1"
}

report_run_start() { # type -> prints run id
  psql_platform "INSERT INTO backup_runs (id, backup_type, status, started_at)
    VALUES (gen_random_uuid(), '$1', 'running', now()) RETURNING id;"
}
report_run_finish() { # id status repo_size_bytes(optional)
  local size="${3:-NULL}"
  psql_platform "UPDATE backup_runs SET status='$2', finished_at=now(),
    repo_size_bytes=${size} WHERE id='$1';"
}
claim_verification() { # id -> mark running, set started_at
  psql_platform "UPDATE backup_verifications SET status='running', started_at=now()
    WHERE id='$1';"
}
finish_verification() { # id status detail
  psql_platform "UPDATE backup_verifications SET status='$2', finished_at=now(),
    detail=\$\$${3:-}\$\$ WHERE id='$1';"
}
insert_scheduled_verification() { # -> prints id (requested, requested_by NULL)
  psql_platform "INSERT INTO backup_verifications (id, status)
    VALUES (gen_random_uuid(), 'requested') RETURNING id;"
}
repo_size_bytes() { # prints total repo bytes via pgbackrest info, or NULL
  pgbr info --output=json 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(b['info']['repository']['size'] for s in d for b in s['backup']) or 'NULL')" 2>/dev/null \
    || echo NULL
}
