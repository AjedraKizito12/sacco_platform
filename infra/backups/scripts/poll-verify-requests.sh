#!/usr/bin/env bash
# Every minute: if a verification is 'requested', claim it and run the drill.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib.sh"

ID="$(psql_platform "SELECT id FROM backup_verifications WHERE status='requested' ORDER BY created_at LIMIT 1;")"
[ -z "$ID" ] && exit 0

claim_verification "$ID"
if "$DIR/restore-staging.sh" "$ID"; then
  :
else
  echo "drill failed for $ID"
fi
