#!/usr/bin/env bash
# Physically archive every tenant the app has flagged ready:
# pg_dump the schema -> age-encrypt -> upload to object storage -> DROP SCHEMA
# CASCADE -> write archive telemetry back into platform.tenants.
#
# The app is the source of the "ready" signal (lifecycle_state='archived' AND
# archive_checksum IS NULL, set by the daily beat). This script is the ONLY
# writer of the archive_* columns and the ONLY code that DROPs a tenant schema.
# It never runs as root; DB access uses the postgres role. See README.md.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib.sh"

WORKDIR="$(mktemp -d)"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

archived=0
while IFS=$'\t' read -r tenant_id schema_name; do
  [ -n "${tenant_id:-}" ] || continue
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  key="offboarding/${schema_name}-${ts}.sql.age"
  local_file="${WORKDIR}/${schema_name}-${ts}.sql.age"

  echo "archiving ${schema_name} (tenant ${tenant_id}) -> ${key}"

  # 1. Dump + encrypt in one stream. age recipient (public key) is host-only;
  #    the private key never lives on this host, so archives are write-only here.
  if ! pg_dump_schema "$schema_name" | age -r "$AGE_RECIPIENT" -o "$local_file"; then
    echo "  ERROR: dump/encrypt failed for ${schema_name}; skipping" >&2
    continue
  fi

  size_bytes="$(stat -c %s "$local_file")"
  checksum="sha256:$(sha256sum "$local_file" | awk '{print $1}')"

  # 2. Upload before dropping anything.
  if ! s3 cp "$local_file" "s3://${OFFBOARDING_BUCKET}/${key}"; then
    echo "  ERROR: upload failed for ${schema_name}; schema left intact" >&2
    continue
  fi

  # 3. Physical drop, then write telemetry back. Order matters: the schema is
  #    gone only after the encrypted object is durably stored.
  drop_schema "$schema_name"
  record_archive "$tenant_id" "$key" "$size_bytes" "$checksum"
  rm -f "$local_file"
  archived=$((archived + 1))
  echo "  done: ${size_bytes} bytes, ${checksum}"
done < <(list_archive_ready)

echo "offboarding archive complete: ${archived} tenant(s) archived"
