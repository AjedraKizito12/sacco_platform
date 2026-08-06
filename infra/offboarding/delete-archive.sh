#!/usr/bin/env bash
# Purge the encrypted archive object for every tenant the app has advanced to
# lifecycle_state='hard_deleted' (past the ~7-year retention window). Deletes the
# object from storage, then nulls archive_storage_key so it is not re-attempted.
#
# The schema is already gone (dropped by archive.sh at the 'archived' step); this
# only removes the long-term encrypted dump. Runs weekly. Never runs as root.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib.sh"

purged=0
while IFS=$'\t' read -r tenant_id storage_key; do
  [ -n "${tenant_id:-}" ] || continue
  echo "purging archive for hard-deleted tenant ${tenant_id}: ${storage_key}"
  if ! s3 rm "s3://${OFFBOARDING_BUCKET}/${storage_key}"; then
    echo "  ERROR: delete failed for ${storage_key}; key left set for retry" >&2
    continue
  fi
  clear_archive_key "$tenant_id"
  purged=$((purged + 1))
done < <(list_hard_deleted_with_archive)

echo "offboarding archive purge complete: ${purged} object(s) removed"
