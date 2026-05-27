# Credit v1a — Implementation Plan Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan sub-plan by sub-plan.
> Execute sub-plans in the order shown in §4. Stop at each sub-plan boundary and run the
> verification criteria before proceeding to the next.

**Goal:** Implement the full loan lifecycle — products, applications, disbursement, repayment
schedules, repayments, interest accrual, penalties (via fees engine), arrears tracking,
write-off, and nightly reconciliation — as a self-contained `app/modules/credit/` module
following the shared sub-ledger accounting model documented in the design spec.

**Design spec:** `docs/superpowers/specs/2026-05-27-credit-v1a-design.md`

---

## 1. Sub-Plan List

| # | File | What it produces |
|---|------|-----------------|
| 01 | `01-schema-and-models.md` | Migration 010, all SQLAlchemy models, conftest wiring, `EXTERNAL_CREDIT`/`EXTERNAL_DEBIT` savings types, `sub_ledger_type`/`sub_ledger_id` on `journal_lines` |
| 02 | `02-loan-products.md` | `LoanProductService` (CRUD), schemas, product API endpoints, seed data |
| 03 | `03-loan-applications.md` | `LoanApplicationService` (submit/withdraw/reject), `ApprovalService` wiring, `credit.approve_application` executor, application API endpoints |
| 04 | `04-disbursement.md` | `LoanDisbursementService` (GL post, savings `record_external_credit`, loan row creation, status → disbursed), disbursement API endpoint |
| 05 | `05-repayment-schedule.md` | `_schedule.py` pure helpers (flat + reducing balance annuity math), `loan_installments` population at disbursement, schedule API endpoint |
| 06 | `06-interest-accrual.md` | `accrue_reducing_balance_interest` Celery beat task, flat interest GL booking at disbursement (retrofit into 04), `accrued_interest` snapshot updates |
| 07 | `07-repayment.md` | `LoanRepaymentService.apply_repayment` (interest-first allocation, installment updates, snapshot updates, GL post, closure detection), repayment API endpoint |
| 08 | `08-penalty-integration.md` | Outbox consumer for `FeeAssessmentCreated`/`FeeCollectionCreated` (`target_type='loan'`), `accrued_penalties` snapshot updates, `CreditQueryService.find_loans_eligible_for_fee`, fees engine wiring |
| 09 | `09-arrears.md` | `mark_loans_in_arrears` beat task, `in_arrears` ↔ `disbursed` status transitions, overdue installment detection |
| 10 | `10-write-off.md` | `LoanWriteOffService` (direct path + maker-checker path for amounts above threshold), `credit.write_off` executor, write-off API endpoint |
| 11 | `11-reconciliation.md` | `reconcile_loan_snapshots` beat task (per-tenant GL-vs-snapshot diff), structured alert on drift, audit entry |
| 12 | `12-api-and-permissions.md` | Full API router wiring, HTTP header dependencies (`X-Tenant-Slug`, `X-Actor-ID`), error mapping, integration tests for all endpoints |
| 13 | `13-claude-md-and-ci.md` | `CLAUDE.md` credit module contracts, `app/main.py` wiring, `celery_app.py` beat schedule, CI ripgrep check for snapshot column writes |

---

## 2. Dependency Graph

```
01 (schema + models)
 ├─▶ 02 (products)
 │    └─▶ 03 (applications)
 │         └─▶ 04 (disbursement) ◀─── 05 (schedule helpers)
 │                  └─▶ 06 (interest accrual)
 │                  └─▶ 07 (repayment) ◀── 05
 │                  └─▶ 08 (penalty integration)
 │                  └─▶ 09 (arrears)
 │                  └─▶ 10 (write-off)
 │
 ├─▶ 05 (schedule helpers)  [pure functions, no DB — can be done before 04]
 │
 └─▶ 11 (reconciliation)   [depends on 04, 06, 07, 08, 10 all being present]
      └─▶ 12 (API + permissions)  [depends on 02–10]
           └─▶ 13 (CLAUDE.md + CI)
```

**Critical path:** 01 → 02 → 03 → 05 → 04 → 07 → 12 → 13

---

## 3. Execution Order

Execute sub-plans in this sequence. Each must pass its verification criteria before the next begins.

```
01 → 02 → 03 → 05 → 04 → 06 → 07 → 08 → 09 → 10 → 11 → 12 → 13
```

**Why 05 before 04:** Sub-plan 04 (disbursement) calls `compute_schedule()` from `_schedule.py`.
The schedule helpers must exist and be tested before disbursement is implemented.

**Why 06 after 04:** Interest accrual beat task operates on disbursed loans. The Celery task
and its GL-posting logic are written after disbursement exists and its tests pass.

**Why 11 after 10:** Reconciliation compares GL sums against all snapshot-mutating operations
(disbursement, repayment, accrual, write-off). All those operations must exist before the
reconciliation query can be written and verified against known test data.

---

## 4. Per-Sub-Plan Reference

### 01 — Schema and Models

**Required reading before starting:**
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §3 (Data Model), §13 (Migration)
- `app/modules/ledger/models.py` — current `JournalLine` definition
- `app/modules/savings/models.py` — current `SavingsTransaction` CHECK constraints
- `alembic/tenant/versions/009_fees_tables.py` — migration pattern to follow
- `tests/conftest.py` — model import pattern + sequence creation

**Produces:**
- `alembic/tenant/versions/010_credit_tables.py`
- `app/modules/credit/__init__.py`, `app/modules/credit/models.py`
- `app/modules/credit/services/__init__.py`
- Updated `app/modules/ledger/models.py` (`sub_ledger_type`, `sub_ledger_id` on `JournalLine`)
- Updated `app/modules/savings/models.py` (`EXTERNAL_CREDIT`, `EXTERNAL_DEBIT` in CHECK)
- Updated `tests/conftest.py` (import credit models, create `loan_number_seq`)
- Updated `app/modules/ledger/service.py` (`post_journal_entry` passes sub_ledger fields)

**Verification criteria:**
- `alembic upgrade head` runs without error on a clean test DB
- `pytest tests/modules/credit/ -v` collects (even if no tests yet — no import errors)
- `pytest tests/modules/ledger/ -v` still passes (backward-compatible change)
- `pytest tests/modules/savings/ -v` still passes

---

### 02 — Loan Products

**Required reading before starting:**
- Sub-plan 01 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §3.1 (`loan_products` table)
- `app/modules/fees/service.py` and `app/modules/fees/api.py` — pattern for CRUD service + router

**Produces:**
- `app/modules/credit/services/product.py` (`LoanProductService`)
- `app/modules/credit/schemas.py` (initial: product schemas only)
- Product section of `app/modules/credit/api.py`
- `tests/modules/credit/test_service.py` (product tests)

**Verification criteria:**
- `pytest tests/modules/credit/test_service.py -k product -v` passes (create, get, list, deactivate)
- Product with `min_amount > max_amount` raises `ValueError`
- `annual_interest_rate < 0` raises `ValueError`
- `required_approvals < 1` raises `ValueError`

---

### 03 — Loan Applications

**Required reading before starting:**
- Sub-plan 01, 02 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §4 (Status Machine)
- `app/modules/savings/service.py` — `submit_withdrawal` maker-checker pattern
- `app/modules/savings/executors.py` — `@approval_executor` registration pattern
- `app/modules/maker_checker/service.py` — `ApprovalService.submit` / `approve` / `reject`

**Produces:**
- `app/modules/credit/services/application.py` (`LoanApplicationService`)
- `app/modules/credit/executors.py` (`credit.approve_application` executor)
- Application section of `app/modules/credit/schemas.py`
- Application section of `app/modules/credit/api.py`
- `tests/modules/credit/test_service.py` (application tests)

**Verification criteria:**
- Submit application → status=`submitted`, `approval_request_id` populated
- Application for inactive product raises `ValueError`
- `requested_amount` outside `[min_amount, max_amount]` raises `ValueError`
- `requested_term_periods > max_term_periods` raises `ValueError`
- Withdraw by non-originator raises `ValueError`
- Withdraw after first approval action raises `ValueError`
- Approve (quorum=1): executor called → application.status = `approved`
- Approve (quorum=2): first approve → status stays `submitted`/`under_review`; second approve → `approved`
- Self-approval raises `ValueError` (from `ApprovalService`)
- Reject → status = `rejected`

---

### 04 — Disbursement

**Required reading before starting:**
- Sub-plans 01, 02, 03, **05** (completed — schedule helpers must exist first)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §6 (Disbursement), §2.2 (Single-writer discipline)
- `app/modules/savings/service.py` — `system_credit` pattern for `record_external_credit` (to be added in 01)

**Produces:**
- `app/modules/credit/services/disbursement.py` (`LoanDisbursementService`)
- Updated `app/modules/savings/service.py` (`record_external_credit`, `record_external_debit`, updated `get_balance`)
- Disbursement section of `app/modules/credit/schemas.py`
- Disbursement API endpoint in `app/modules/credit/api.py`
- `tests/modules/credit/test_service.py` (disbursement tests)

**Verification criteria:**
- Disburse approved application → `loans` row created, status=`disbursed`, `outstanding_principal` = `approved_amount`
- GL entry: Dr loans_receivable, Cr disbursement account — balanced
- All journal lines tagged `sub_ledger_type='loan'`, `sub_ledger_id=loan.id`
- `member_savings` destination: `savings_transactions` row with `transaction_type=EXTERNAL_CREDIT`, no duplicate GL entry
- Flat method: second GL entry Dr interest_receivable / Cr interest_income posted at disbursement
- Disburse twice with same idempotency_key: second call returns existing loan, exactly one GL entry
- Disburse non-approved application raises `ValueError`
- `loan_installments` rows written: `SUM(principal_due)` = `principal_amount`, `SUM(interest_due)` = `total_interest`
- `loan_number_seq` used: `loan_reference` matches `LN-{YYYYMM}-{seq:06d}`

---

### 05 — Repayment Schedule Generation

**Required reading before starting:**
- Sub-plan 01 (completed — models must exist)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §5 (Interest Calculation)

**Produces:**
- `app/modules/credit/services/_schedule.py` (pure functions: `compute_schedule`)
- `tests/modules/credit/test_schedule.py` (unit tests — no DB required)

**Verification criteria (unit tests only — no DB):**
- **Flat, monthly, 12 periods:** `SUM(principal_due)` = principal; `SUM(interest_due)` = `principal × rate × 1`; all installments equal
- **Flat, quarterly, 4 periods:** interest = `principal × rate × 1`; installments equal
- **Reducing balance, monthly, 12 periods:** annuity formula verified; `SUM(principal_due)` = principal (within ±1 minor unit rounding tolerance); interest front-loaded (period 1 interest > period 12 interest)
- **Reducing balance, 0% rate:** all interest_due = 0; installments are pure principal splits
- **Single-period (lump sum equivalent — term_periods=1):** one installment, due_date computed, total_due = principal + interest
- **Due dates:** weekly → 7-day gaps; monthly → calendar-month gaps; quarterly → 3-month gaps

---

### 06 — Interest Accrual

**Required reading before starting:**
- Sub-plans 01, 04, 05 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §5.2, §8 (Beat Jobs)
- `app/modules/fees/beat.py` — Celery beat task pattern with per-tenant loop

**Produces:**
- `app/modules/credit/beat.py` (`accrue_reducing_balance_interest` task — initial version)
- Updated `app/workers/celery_app.py` (register beat task)
- `tests/modules/credit/test_service.py` (accrual tests)

**Verification criteria:**
- Reducing balance loan, day after disbursement: beat task posts GL Dr interest_receivable / Cr interest_income for period 1 interest amount
- Same task run twice on same day: idempotent (no duplicate GL entry)
- Flat method loan: beat task does nothing (interest booked at disbursement)
- `accrued_interest` snapshot updated after accrual
- All accrual GL lines tagged `sub_ledger_type='loan'`

---

### 07 — Repayment

**Required reading before starting:**
- Sub-plans 01, 04, 05, 06 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §7 (Repayment), §2.2 (Single-writer)
- `app/modules/savings/service.py` — `record_external_debit` (added in 04)

**Produces:**
- `app/modules/credit/services/repayment.py` (`LoanRepaymentService.apply_repayment`)
- Repayment section of `app/modules/credit/schemas.py`
- Repayment API endpoint in `app/modules/credit/api.py`
- Updated `tests/modules/credit/test_service.py` (repayment tests)

**Verification criteria:**
- Interest-first: repayment of 500 when `accrued_interest=200`, `outstanding_principal=2000` → `interest_applied=200`, `principal_applied=300`
- Exact payoff: repayment = `outstanding_principal + accrued_interest` → loan status = `closed`, `closed_at` set
- Overpayment: `amount > total owed` → `overpayment > 0`, `outstanding_principal = 0`, status = `closed`
- GL balanced: `SUM(debit_amounts) == SUM(credit_amounts)` on repayment entry
- GL lines tagged `sub_ledger_type='loan'`
- `outstanding_principal`, `total_paid_principal`, `total_paid_interest` snapshots updated correctly
- `loan_installments` updated: oldest installments marked paid in sequence
- Idempotency: same `idempotency_key` twice → second call returns existing repayment, one GL entry
- `member_savings` source: `savings_transactions` row with `transaction_type=EXTERNAL_DEBIT`
- Repayment on closed loan raises `ValueError`

---

### 08 — Penalty Integration

**Required reading before starting:**
- Sub-plans 01, 04, 07 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §2.3 (Penalties — zero cross-module dependency)
- `app/modules/fees/consumer.py` — outbox consumer + `processed_events` idempotency pattern
- `app/modules/fees/models.py` — `FeeAssessment` structure (`target_type`, `target_id`)
- `app/modules/fees/service.py` — `FeeAssessmentService.assess` signature

**Produces:**
- `app/modules/credit/consumer.py` (outbox consumer for `FeeAssessmentCreated`, `FeeCollectionCreated` where `target_type='loan'`)
- `app/modules/credit/services/query.py` (`CreditQueryService.find_loans_eligible_for_fee`)
- Updated `app/workers/celery_app.py` (register consumer)
- `tests/modules/credit/test_service.py` (penalty snapshot tests)

**Verification criteria:**
- `FeeAssessmentCreated` event for `target_type='loan'` → `loans.accrued_penalties` incremented
- `FeeCollectionCreated` event for `target_type='loan'` → `loans.accrued_penalties` decremented, `total_paid_penalties` incremented
- Consumer idempotent: replayed event → no second update
- `find_loans_eligible_for_fee` returns loans whose most recent installment is overdue by `≥ penalty_days_past_due` threshold
- No direct import of any `app.modules.fees.*` service in consumer (only model selects + event payload parsing)
- `accrued_penalties` never goes below zero (test floor guard)

---

### 09 — Arrears and Derived Status

**Required reading before starting:**
- Sub-plans 01, 04, 07 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §4 (Status Machine)
- `app/modules/credit/beat.py` (partial — from 06)

**Produces:**
- `mark_loans_in_arrears` task added to `app/modules/credit/beat.py`
- Updated `app/workers/celery_app.py`
- `tests/modules/credit/test_service.py` (arrears tests)

**Verification criteria:**
- Loan with one overdue installment → beat task sets `status=in_arrears`
- Loan with all installments paid up to date → beat task clears `in_arrears` → `disbursed`
- Beat task is idempotent: run twice on same day → no double status flips
- `closed` and `written_off` loans are excluded from arrears processing
- `draft`/`submitted`/`approved` applications are unaffected

---

### 10 — Write-Off

**Required reading before starting:**
- Sub-plans 01, 04, 07 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §9 (Write-Off)
- `app/modules/savings/executors.py` — `@approval_executor` pattern
- `app/modules/maker_checker/service.py` — `ApprovalService.submit`

**Produces:**
- `app/modules/credit/services/write_off.py` (`LoanWriteOffService`)
- `credit.write_off` executor added to `app/modules/credit/executors.py`
- Write-off API endpoint in `app/modules/credit/api.py`
- `tests/modules/credit/test_service.py` (write-off tests)

**Verification criteria:**
- Amount ≤ `write_off_threshold`: direct execution, no approval_request created
- Amount > `write_off_threshold`: `approval_request` created, GL not posted until quorum met
- GL: Dr `loan_loss_expense` account / Cr `gl_principal_receivable_id` — balanced
- GL lines tagged `sub_ledger_type='loan'`
- `outstanding_principal` decremented, `total_written_off` incremented
- Status → `written_off`
- Write-off on already-`written_off` loan raises `ValueError`
- Write-off amount > `outstanding_principal` raises `ValueError`
- Self-approval raises `ValueError` (enforced by `ApprovalService`)
- Idempotency: executor called twice with same idempotency_key → second call is no-op

---

### 11 — Reconciliation

**Required reading before starting:**
- Sub-plans 01, 04, 06, 07, 08, 10 (completed — all financial operations must exist)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §8 (Beat Jobs — reconciliation)
- `app/modules/credit/beat.py` (partial — from 06, 09)

**Produces:**
- `reconcile_loan_snapshots` task added to `app/modules/credit/beat.py`
- `tests/modules/credit/test_service.py` (reconciliation tests)

**Verification criteria:**
- After a full loan lifecycle (disburse → repay → close): reconciliation finds no drift
- Injected drift test: directly UPDATE `loans.outstanding_principal` bypassing service → reconciliation detects the mismatch
- Reconciliation logs a structured error (`loan_snapshot_drift` event) and writes an `audit_log` entry for each drifted loan
- Reconciliation does NOT modify the loan row (read-only + alert only)
- Beat task is per-tenant: runs on all active tenant schemas
- Only `disbursed`, `in_arrears`, and `written_off` loans are checked (not `closed`, `draft`, etc.)

---

### 12 — API and Permissions

**Required reading before starting:**
- Sub-plans 01–11 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §10 (API Endpoints)
- `app/modules/fees/api.py` — router pattern
- `tests/modules/savings/test_api.py` — API integration test pattern

**Produces:**
- Completed `app/modules/credit/api.py` (all 18 endpoints wired)
- `tests/modules/credit/test_api.py` (API integration tests)

**Verification criteria (one test per endpoint):**
- `POST /credit/products` → 201
- `GET /credit/products` → 200, list
- `GET /credit/products/{id}` → 200; unknown id → 404
- `POST /credit/applications` → 201, status=`submitted`
- `POST /credit/applications/{id}/approve` → 200 (quorum=1 → status=`approved`)
- `POST /credit/applications/{id}/reject` → 200, status=`rejected`
- `POST /credit/applications/{id}/withdraw` → 200
- `POST /credit/loans/{application_id}/disburse` → 201, `outstanding_principal` = amount
- `GET /credit/loans/{id}` → 200, balance fields present
- `GET /credit/loans/{id}/schedule` → 200, installment list, `SUM(total_due)` correct
- `POST /credit/loans/{id}/repayments` → 201
- `GET /credit/loans/{id}/repayments` → 200, list
- `POST /credit/loans/{id}/write-off` (below threshold) → 201
- Missing `X-Tenant-Slug` → 422 or middleware-handled error
- Unknown loan id → 404

---

### 13 — CLAUDE.md and CI Rules

**Required reading before starting:**
- Sub-plans 01–12 (completed)
- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §14 (CLAUDE.md Additions)
- Current `CLAUDE.md`

**Produces:**
- `CLAUDE.md` — credit module contracts section appended
- `app/main.py` — credit router + executor imports added
- `app/workers/celery_app.py` — all credit beat tasks and consumer registered (final state)
- CI ripgrep check documented (can be a `scripts/check_credit_snapshot_writes.sh` or inline `Makefile` rule)

**Verification criteria:**
- `python -c "from app.main import app"` — no import errors
- `pytest -x -q` — full test suite passes (no regressions)
- Ripgrep check: `rg 'outstanding_principal|accrued_interest|accrued_penalties|total_paid_' --type py app/` — all matches inside `app/modules/credit/services/`
- `rg 'system_debit\|system_credit' --type py app/modules/credit/` — no matches (credit module uses `record_external_*` not `system_*`)
- Beat schedule: `celery -A app.workers.celery_app inspect registered` lists all 5 credit tasks

---

## 5. Cross-Cutting Concerns

These apply to every sub-plan. Each sub-plan's verification criteria implicitly includes them.

### Single-writer discipline (snapshot columns)
Every method that writes `outstanding_principal`, `accrued_interest`, `accrued_penalties`,
`total_paid_*`, or `total_written_off` must:
1. Open with `SELECT loans ... FOR UPDATE` on the loan row
2. Call `LedgerService.post_journal_entry(...)` before updating snapshot columns
3. Write all changes (GL + snapshot + `loan_repayments`/audit) in one DB transaction

Sub-plan 13 adds the CI grep check that enforces this statically.

### sub_ledger tagging
Every `journal_line` written by the credit module must carry `sub_ledger_type='loan'`
and `sub_ledger_id=loan.id`. Sub-plan 01 adds these columns to `journal_lines`.
Sub-plan 04 (and every subsequent financial operation) tags its lines.

### Idempotency
Every service method that posts a GL entry must have an idempotency guard:
- Check for existing row by `idempotency_key` before doing any work
- Return existing row on hit
- The `idempotency_key` passed to `LedgerService.post_journal_entry` must be prefixed
  to be globally unique (e.g. `"loan-disb-{key}"`, `"loan-rpy-{key}"`).

### Outbox events
Every material state change publishes an outbox event via `EventPublisher.publish(...)`.
See §12 of the design spec for the event catalogue.

### Audit log
Every service method that creates or transitions a `loans` or `loan_applications` row
must call `TenantAuditService.record(...)` with `before_state` / `after_state`.

---

## 6. File Map

```
app/modules/credit/
  __init__.py
  models.py
  schemas.py
  api.py
  executors.py          credit.approve_application, credit.write_off
  consumer.py           FeeAssessmentCreated / FeeCollectionCreated handler
  beat.py               accrue_reducing_balance_interest, mark_loans_in_arrears,
                        reconcile_loan_snapshots
  services/
    __init__.py
    product.py          LoanProductService
    application.py      LoanApplicationService
    disbursement.py     LoanDisbursementService
    repayment.py        LoanRepaymentService
    write_off.py        LoanWriteOffService
    query.py            CreditQueryService
    _schedule.py        compute_schedule (pure functions, no DB)

alembic/tenant/versions/
  010_credit_tables.py

tests/modules/credit/
  __init__.py
  test_schedule.py      unit tests (no DB)
  test_service.py       integration tests
  test_api.py           API integration tests

Modified files:
  app/modules/ledger/models.py         sub_ledger_type, sub_ledger_id on JournalLine
  app/modules/ledger/service.py        post_journal_entry passes sub_ledger fields
  app/modules/savings/models.py        EXTERNAL_CREDIT, EXTERNAL_DEBIT in CHECK
  app/modules/savings/service.py       record_external_credit, record_external_debit, get_balance
  app/main.py                          credit router + executor imports
  app/workers/celery_app.py            credit beat + consumer tasks
  tests/conftest.py                    import credit models, create loan_number_seq
  CLAUDE.md                            credit module contracts
```

---

## 7. Known Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Snapshot drift from concurrent transactions | `SELECT ... FOR UPDATE` on loan row in every write path; reconciliation beat catches any missed cases |
| Flat vs reducing GL treatment divergence | Test both paths in sub-plan 05 (pure math) and sub-plan 04 (GL); reconciliation in sub-plan 11 validates both |
| Savings `record_external_credit` missing in production but not test | Sub-plan 04 integration test uses full `SavingsService`; not mocked |
| Migration 010 breaks existing tests | Sub-plan 01 runs full test suite before moving on |
| Circular import between credit and savings | Both `record_external_credit` and `record_external_debit` are called inside local imports within the disbursement/repayment service methods, consistent with `fees/service.py` pattern |
| Fees engine calling `find_loans_eligible_for_fee` before it exists | Sub-plan 08 adds the method AND updates the fees engine's schedule job caller; both changes ship together |
