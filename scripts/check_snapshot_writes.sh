#!/usr/bin/env bash
# CI check: loan snapshot column writes must only occur inside app/modules/credit/services/
# Run: bash scripts/check_snapshot_writes.sh
# Exit 0 = clean, Exit 1 = violation found

set -euo pipefail

SNAPSHOT_COLS="outstanding_principal|accrued_interest|accrued_penalties|total_paid_principal|total_paid_interest|total_paid_penalties|total_written_off"

echo "Checking snapshot column writes are confined to app/modules/credit/services/ ..."

# Find all matches outside the credit services directory.
VIOLATIONS=$(rg -l "$SNAPSHOT_COLS" --type py app/ \
    --glob '!app/modules/credit/services/**' \
    --glob '!app/modules/credit/models.py' \
    2>/dev/null || true)

if [ -n "$VIOLATIONS" ]; then
    echo ""
    echo "ERROR: Snapshot column writes found outside app/modules/credit/services/:"
    echo "$VIOLATIONS"
    echo ""
    echo "All writes to loan snapshot columns must go through the credit services."
    echo "See CLAUDE.md '## Credit module contracts'."
    exit 1
fi

echo "OK: No snapshot column writes found outside app/modules/credit/services/"

# Also check that credit module never calls system_debit/system_credit.
echo "Checking credit module does not call system_debit/system_credit ..."

SAVINGS_DIRECT=$(rg -l "system_debit|system_credit" --type py app/modules/credit/ 2>/dev/null || true)

if [ -n "$SAVINGS_DIRECT" ]; then
    echo ""
    echo "ERROR: Direct system_debit/system_credit calls found in credit module:"
    echo "$SAVINGS_DIRECT"
    echo ""
    echo "Use SavingsService.record_external_credit / record_external_debit instead."
    exit 1
fi

echo "OK: No system_debit/system_credit in credit module"
echo ""
echo "All checks passed."
