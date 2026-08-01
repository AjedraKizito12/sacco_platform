#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib.sh"

# Expire per the retention policy in pgbackrest.conf (repo1-retention-full).
pgbr expire
