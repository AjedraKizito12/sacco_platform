# Sub-plan 13 — CLAUDE.md and CI Rules

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`. Complete all tasks in order. Run verification criteria
> at the end before marking this sub-plan done.

**Goal:** Wire the credit module into `app/main.py`, finalise `app/workers/celery_app.py`,
add credit module contracts to `CLAUDE.md`, and add a CI ripgrep check that enforces the
single-writer discipline for loan snapshot columns.

**Architecture:** This is the integration and documentation sub-plan. No new business
logic — just wiring, documentation, and static analysis.

**Tech Stack:** Python imports, ripgrep

---

## Required Reading

- Sub-plans 01–12 (completed — all code exists)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §14 (CLAUDE.md Additions)
- Current `CLAUDE.md` (read before editing)
- Current `app/main.py` (read before editing)
- Current `app/workers/celery_app.py` (read before editing)

---

## File Map

```
Modified
  app/main.py                  add credit router + executor import
  app/workers/celery_app.py    final state with all credit tasks registered
  CLAUDE.md                    credit module contracts appended
  scripts/check_snapshot_writes.sh   CI check (new file)
```

---

## Task 1 — Wire Credit Router into `app/main.py`

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Read `app/main.py`**

Read the file to see how existing routers (savings, fees, etc.) are included.

- [ ] **Step 2: Add credit router and executor imports**

In `app/main.py`, add the credit router import alongside the other module routers:

```python
from app.modules.credit.api import router as credit_router
```

Add the executor import (registering the executor functions with `@approval_executor`):

```python
import app.modules.credit.executors  # noqa: F401  — registers @approval_executor callbacks
```

Include the router in the FastAPI app (follow the pattern used for savings/fees):

```python
app.include_router(credit_router)
```

- [ ] **Step 3: Verify app starts**

```bash
python -c "from app.main import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat(credit): wire credit router + executors into app/main.py"
```

---

## Task 2 — Finalise `app/workers/celery_app.py`

**Files:**
- Modify: `app/workers/celery_app.py`

- [ ] **Step 1: Read `app/workers/celery_app.py`**

Read the current file. Verify all five credit tasks are present. The final `include` list
and `beat_schedule` should look like this:

```python
celery_app = Celery(
    "sacco",
    broker=settings.redis_url,
    include=[
        "app.core.outbox.worker",
        "app.core.outbox.retention",
        "app.platform_.provisioning.tasks",
        "app.modules.iam.beat",
        "app.modules.fees.consumer",
        "app.modules.fees.beat",
        "app.modules.credit.beat",
        "app.modules.credit.consumer",
    ],
)
```

Beat schedule additions (should already be present from sub-plans 06, 08, 09, 11):

```python
        "accrue-reducing-balance-interest": {
            "task": "app.modules.credit.beat.accrue_reducing_balance_interest",
            "schedule": 24 * 3600.0,  # daily
        },
        "mark-loans-in-arrears": {
            "task": "app.modules.credit.beat.mark_loans_in_arrears",
            "schedule": 24 * 3600.0,  # daily
        },
        "reconcile-loan-snapshots": {
            "task": "app.modules.credit.beat.reconcile_loan_snapshots",
            "schedule": 24 * 3600.0,  # daily
        },
        "consume-credit-events": {
            "task": "app.modules.credit.consumer.consume_credit_events",
            "schedule": 60.0,  # every minute
        },
```

If any of these entries are missing, add them now.

- [ ] **Step 2: Verify all tasks**

```bash
python -c "
from app.workers.celery_app import celery_app
sched = celery_app.conf.beat_schedule
required = [
    'accrue-reducing-balance-interest',
    'mark-loans-in-arrears',
    'reconcile-loan-snapshots',
    'consume-credit-events',
]
for name in required:
    assert name in sched, f'Missing beat task: {name}'
print('All credit tasks registered OK')
"
```

Expected: `All credit tasks registered OK`

- [ ] **Step 3: Commit if changes were made**

```bash
git add app/workers/celery_app.py
git commit -m "chore(credit): finalise celery_app.py — all credit tasks registered"
```

(Skip commit if no changes needed.)

---

## Task 3 — Add Credit Module Contracts to CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Read CLAUDE.md**

Read the current `CLAUDE.md` to find the correct insertion point (after the Fees module
contracts section).

- [ ] **Step 2: Append credit module contracts**

Add the following section after `## Fees module contracts (do not violate)`:

```markdown
## Credit module contracts (do not violate)
- Loan balance snapshot (`loans.outstanding_principal`, `accrued_interest`, `accrued_penalties`,
  `total_paid_principal`, `total_paid_interest`, `total_paid_penalties`, `total_written_off`) is
  the authoritative source for operational balance queries. GL is authoritative for
  accounting reports. The two are reconciled nightly by `reconcile_loan_snapshots`.
- All snapshot updates happen inside `app/modules/credit/services/` in a single transaction
  with the matching GL post. No other code path may UPDATE the snapshot columns.
  CI enforces this with a ripgrep check (see `scripts/check_snapshot_writes.sh`).
- Every `journal_line` produced by a credit operation must carry `sub_ledger_type='loan'`
  and `sub_ledger_id=loan.id`. Lines without `sub_ledger_id` are not queryable in the
  loan sub-ledger.
- Loan penalties are fees. The authoritative penalty record is `fee_assessments` with
  `target_type='loan'`. The credit module snapshots `accrued_penalties`; it does not store
  penalty history. There is no `loan_penalty_charges` table.
- Loan write-off is the only operation that decreases `outstanding_principal` without a
  member payment. It requires maker-checker with quorum=2 above the product's
  `write_off_threshold`.
- `SavingsService.record_external_credit` and `record_external_debit` are the only permitted
  paths for the credit module to create savings transaction rows. Never call savings
  `system_debit`/`system_credit` from the credit module.
- `CreditQueryService.find_loans_eligible_for_fee` is the only cross-module interface
  the fees engine may call into the credit module. No other direct calls between modules.
- Direct execution paths for `credit.write_off` (below `write_off_threshold`) and
  `credit.approve_application` are registered via `@approval_executor` in
  `app/modules/credit/executors.py`. Do not add alternate execution paths.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(credit): add credit module contracts to CLAUDE.md"
```

---

## Task 4 — CI Ripgrep Check for Snapshot Column Writes

**Files:**
- Create: `scripts/check_snapshot_writes.sh`

- [ ] **Step 1: Create `scripts/check_snapshot_writes.sh`**

```bash
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
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/check_snapshot_writes.sh
```

- [ ] **Step 3: Run the check**

```bash
bash scripts/check_snapshot_writes.sh
```

Expected: `All checks passed.`

If violations are reported, fix them before committing.

- [ ] **Step 4: Commit**

```bash
git add scripts/check_snapshot_writes.sh
git commit -m "ci(credit): add ripgrep check for snapshot column write discipline"
```

---

## Verification Criteria

```bash
# 1. App starts cleanly
python -c "from app.main import app; print('OK')"

# 2. Full test suite — no regressions
pytest -x -q

# 3. All credit beat tasks registered
python -c "
from app.workers.celery_app import celery_app
sched = celery_app.conf.beat_schedule
required = [
    'accrue-reducing-balance-interest',
    'mark-loans-in-arrears',
    'reconcile-loan-snapshots',
    'consume-credit-events',
]
for name in required:
    assert name in sched, f'Missing: {name}'
print('All 4 credit tasks registered OK')
"

# 4. CI snapshot check passes
bash scripts/check_snapshot_writes.sh

# 5. Credit router wired
python -c "
from app.main import app
routes = [r.path for r in app.routes]
assert any('/credit/' in r for r in routes), 'Credit router not wired'
print('Credit router wired OK')
"
```

All commands must exit 0. Confirm:
- `python -c "from app.main import app"` — no import errors
- `pytest -x -q` — full test suite passes (no regressions)
- Ripgrep check: all snapshot column writes confined to `app/modules/credit/services/`
- No `system_debit`/`system_credit` calls in `app/modules/credit/`
- Beat schedule lists all 4 credit tasks
- Credit router responds to requests (verified by API tests in sub-plan 12)
