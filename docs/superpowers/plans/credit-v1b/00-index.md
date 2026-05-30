# Credit v1b — Implementation Plan Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan sub-plan by sub-plan.
> Execute sub-plans in the order shown in §4. Stop at each sub-plan boundary and run the
> verification criteria before proceeding to the next.

**Goal:** Extend the credit module with guarantors (hard lien on savings), schedule
restructuring (term extension + payment holiday), bulk payroll-deduction repayments,
loan statements (JSON + PDF), and write-off recovery.

**Design spec:** `docs/superpowers/specs/2026-05-28-credit-v1b-design.md`

---

## 1. Sub-Plan List

| # | File | What it produces |
|---|------|-----------------|
| 01 | `01-migration-and-models.md` | Migration 012, new SQLAlchemy models, field additions to LoanProduct/LoanInstallment, conftest wiring |
| 02 | `02-guarantors.md` | `GuarantorService` (nominate/accept/decline/place/adjust/release/reactivate), `SavingsService.get_available_balance`, guarantor API endpoints |
| 03 | `03-restructuring.md` | `LoanRestructuringService`, `credit.restructure_schedule` executor, restructuring API endpoints |
| 04 | `04-payroll-batches.md` | `PayrollBatchService` (CSV + JSON submit, preview, apply), `credit.apply_payroll_batch` executor, payroll API endpoints |
| 05 | `05-write-off-recovery.md` | `LoanWriteOffService.recover()`, lien reactivation hook, recovery API endpoint |
| 06 | `06-loan-statements.md` | `LoanStatementService` (JSON + PDF via WeasyPrint), statement API endpoints |
| 07 | `07-integration.md` | Wire guarantor hooks into disbursement/repayment/write-off; update CLAUDE.md; update CI snapshot check |

---

## 2. Dependency Graph

```
01 (migration + models)
 ├─▶ 02 (guarantors)
 │    └─▶ 03 (restructuring)      [restructuring independent but needs guarantors wired into repayment first]
 │    └─▶ 04 (payroll)            [payroll calls LoanRepaymentService which must have lien hooks]
 │    └─▶ 05 (write-off recovery) [recovery reactivates guarantor liens]
 │    └─▶ 06 (statements)         [statements independent but needs all financial ops to exist]
 │
 └─▶ 07 (integration)             [must come last — wires everything together]
```

**Critical path:** 01 → 02 → 07 (guarantor hooks in disbursement/repayment/write-off)

---

## 3. Execution Order

```
01 → 02 → 03 → 04 → 05 → 06 → 07
```

Each sub-plan must pass its verification criteria before the next begins.

---

## 4. Per-Sub-Plan Reference

### 01 — Migration and Models

**Required reading:**
- `alembic/tenant/versions/011_la_status_disbursed.py` — migration pattern
- `app/modules/credit/models.py` — current credit models
- `tests/conftest.py` — model import pattern

**Produces:**
- `alembic/tenant/versions/012_credit_v1b_tables.py`
- Updated `app/modules/credit/models.py` (5 new model classes + field additions)
- Updated `tests/conftest.py` (import new models)

**Verification:**
- `alembic upgrade head` runs without error on the test DB
- `pytest tests/modules/credit/ -v` collects without import errors

---

### 02 — Guarantors

**Required reading:**
- Sub-plan 01 (completed)
- Design spec §5 (Guarantor Flows)
- `app/modules/savings/service.py` — `get_balance`, `get_primary_account_for_member`
- `app/modules/credit/services/disbursement.py` — disbursement flow (for integration point)
- `app/modules/credit/services/repayment.py` — repayment flow (for integration point)

**Produces:**
- `app/modules/credit/services/guarantor.py` (`GuarantorService`)
- Updated `app/modules/savings/service.py` (`get_available_balance`)
- Updated `app/modules/credit/api.py` (4 guarantor endpoints)
- Updated `app/modules/credit/schemas.py` (guarantor schemas)
- `tests/modules/credit/test_guarantor_service.py`

**Verification:**
- `pytest tests/modules/credit/test_guarantor_service.py -v` passes
- Nominate on product with `required_guarantors=0` raises `ValueError`
- Accept sets `status=accepted`; decline sets `status=declined`
- `get_available_balance` subtracts active liens from raw balance

---

### 03 — Restructuring

**Required reading:**
- Sub-plan 01, 02 (completed)
- Design spec §6 (Schedule Restructuring Flow)
- `app/modules/credit/services/_schedule.py` — `compute_schedule` (for reuse in restructuring)
- `app/modules/credit/executors.py` — executor pattern

**Produces:**
- `app/modules/credit/services/restructuring.py` (`LoanRestructuringService`)
- Updated `app/modules/credit/executors.py` (`credit.restructure_schedule`)
- Updated `app/modules/credit/api.py` (2 restructuring endpoints)
- Updated `app/modules/credit/schemas.py` (restructuring schemas)
- `tests/modules/credit/test_restructuring_service.py`

**Verification:**
- Term extension: supersedes unpaid installments, writes new ones with correct `term_periods` and `maturity_date`
- Payment holiday: shifts due dates forward by `periods_added`
- Paid installments never superseded
- Requires quorum=2 (direct execution path raises error without approval)

---

### 04 — Payroll Batches

**Required reading:**
- Sub-plan 01, 02, 03 (completed — repayment must have lien hooks)
- Design spec §7 (Bulk Payroll Repayments Flow)
- `app/modules/credit/services/repayment.py` — `apply_repayment` signature

**Produces:**
- `app/modules/credit/services/payroll.py` (`PayrollBatchService`)
- Updated `app/modules/credit/executors.py` (`credit.apply_payroll_batch`)
- Updated `app/modules/credit/api.py` (4 payroll endpoints)
- Updated `app/modules/credit/schemas.py` (payroll schemas)
- `tests/modules/credit/test_payroll_service.py`

**Verification:**
- CSV and JSON parse correctly; matched/unmatched counts correct
- Batch requires approval; applying before approval raises error
- Each matched line applied with idempotency key `payroll-{batch_id}-{line_id}`
- Failed line marks `status=error`; other lines still applied

---

### 05 — Write-Off Recovery

**Required reading:**
- Sub-plan 01, 02 (completed — guarantor reactivation)
- Design spec §8 (Write-Off Recovery Flow)
- `app/modules/credit/services/write_off.py` — `_execute_write_off` pattern

**Produces:**
- Updated `app/modules/credit/services/write_off.py` (`recover()` method)
- Updated `app/modules/credit/api.py` (1 recovery endpoint)
- Updated `app/modules/credit/schemas.py` (recovery schemas)
- `tests/modules/credit/test_write_off_recovery.py`

**Verification:**
- Recovery on non-`written_off` loan raises `ValueError`
- `amount > total_written_off` raises `ValueError`
- GL: Dr principal_receivable / Cr loan_loss_expense — balanced
- `outstanding_principal` restored, `total_written_off` reduced, `status → in_arrears`
- Liens reactivated

---

### 06 — Loan Statements

**Required reading:**
- Sub-plan 01–05 (completed — all financial ops must exist)
- Design spec §9 (Loan Statement)
- `app/modules/ledger/models.py` — `JournalLine`, `JournalEntry` schema
- `app/modules/fees/models.py` — `FeeAssessment`, `FeeCollection` schema

**Produces:**
- `app/modules/credit/services/statement.py` (`LoanStatementService`)
- `app/modules/credit/templates/loan_statement.html` (Jinja2 template)
- Updated `app/modules/credit/api.py` (2 statement endpoints)
- Updated `app/modules/credit/schemas.py` (statement schemas)
- `tests/modules/credit/test_statement_service.py`

**Verification:**
- Statement lines in chronological order; `running_balance` correct after each event
- Date filter returns only lines in range
- PDF endpoint returns `bytes` with correct content

---

### 07 — Integration

**Required reading:**
- Sub-plans 01–06 (all completed)
- Current `app/modules/credit/services/disbursement.py`
- Current `app/modules/credit/services/repayment.py`
- Current `app/modules/credit/services/write_off.py`
- Current `CLAUDE.md`

**Produces:**
- Updated `app/modules/credit/services/disbursement.py` (calls `GuarantorService.place_liens`)
- Updated `app/modules/credit/services/repayment.py` (calls `adjust_liens` + `release_liens`)
- Updated `app/modules/credit/services/write_off.py` (calls `release_liens` on write-off)
- Updated `app/workers/celery_app.py` (no new beat tasks; verify existing still correct)
- Updated `CLAUDE.md` (v1b contracts)
- Updated `scripts/check_snapshot_writes.sh` (include new snapshot columns if any)

**Verification:**
- `python -c "from app.main import app; print('OK')"` — no import errors
- `pytest -x -q` — full suite passes

---

## 5. File Map

```
New files:
  alembic/tenant/versions/012_credit_v1b_tables.py
  app/modules/credit/services/guarantor.py
  app/modules/credit/services/restructuring.py
  app/modules/credit/services/payroll.py
  app/modules/credit/services/statement.py
  app/modules/credit/templates/loan_statement.html
  tests/modules/credit/test_guarantor_service.py
  tests/modules/credit/test_restructuring_service.py
  tests/modules/credit/test_payroll_service.py
  tests/modules/credit/test_statement_service.py
  tests/modules/credit/test_write_off_recovery.py

Modified files:
  app/modules/credit/models.py           5 new model classes + fields on LoanProduct, LoanInstallment
  app/modules/credit/schemas.py          new Pydantic schemas per feature
  app/modules/credit/api.py              13 new endpoints
  app/modules/credit/executors.py        2 new executors
  app/modules/credit/services/disbursement.py    place_liens hook
  app/modules/credit/services/repayment.py       adjust_liens + release_liens hooks
  app/modules/credit/services/write_off.py       release_liens hook + recover()
  app/modules/savings/service.py         get_available_balance()
  tests/conftest.py                      import new models
  app/workers/celery_app.py              verify (no new tasks)
  CLAUDE.md                              v1b contracts
  scripts/check_snapshot_writes.sh       update if new columns added
```

---

## 6. New Dependency

`weasyprint>=62.0` — added to `requirements.txt` (or `pyproject.toml`). Justification: HTML→PDF
rendering for loan statements. No alternative PDF library already in the stack.

---

## 7. Cross-Cutting Concerns

### Lien mutations are always in the same transaction as the financial operation
`place_liens`, `adjust_liens`, `release_liens`, `reactivate_liens` are all called within
the same `session` that owns the disbursement/repayment/write-off/recovery transaction.
They must never open their own session or spawn a background task.

### Single-writer discipline (unchanged from v1a)
No new snapshot columns on `loans`. `GuarantorService` writes to `loan_guarantor_liens`
(its own table), not to `loans` snapshot columns.

### Idempotency
- `GuarantorService.nominate`: idempotency key guards against duplicate nominations
- `LoanRestructuringService.restructure`: idempotency key on `loan_restructurings`
- `PayrollBatchService.apply_batch`: per-line idempotency key `payroll-{batch_id}-{line_id}`
- `LoanWriteOffService.recover`: idempotency key prefix `loan-wor-`
