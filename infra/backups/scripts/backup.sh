#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/lib.sh"

RUN_ID="$(report_run_start full)"
if pgbr backup --type=full; then
  report_run_finish "$RUN_ID" succeeded "$(repo_size_bytes)"
else
  report_run_finish "$RUN_ID" failed
  exit 1
fi
