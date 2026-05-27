# Credit Module v1a — Design Spec
**Date:** 2026-05-27  
**Status:** Approved for implementation  
**Module:** `app/modules/credit/`  
**Depends on:** core, platform_, iam, ledger, members, savings, fees

---

## 1. Scope

Credit v1a covers the full lifecycle of a loan from product configuration through
disbursement, scheduled repayments, interest accrual, late-penalty assessment, and
write-off.

**In scope:**
- Loan products (configurable terms, interest methods, repayment frequencies)
- Loan applications (maker-checker approval, configurable quorum per product)
- Disbursement to member savings account, named cash/bank GL account, or internal GL account
- Full amortisation schedule generated at disbursement
- Repayments (manual capture), interest-first allocation
- Daily interest accrual (reducing balance) / interest-at-disbursement booking (flat)
- Late-payment penalties via the fees engine (zero direct module dependency)
- Loan write-off (maker-checker, quorum=2 above configurable threshold)
- Nightly snapshot reconciliation beat job

**Out of scope (v1b):**
- Guarantors
- Repayment schedule restructuring
- Bulk payroll-deduction repayments
- Loan statements (reporting module)
- Write-off recovery

---

## 2. Architecture

### 2.1 Sub-ledger accounting model (Approach C)

The credit module uses a **shared control account per loan product** with
**line-level tagging** and a **snapshotted balance on the loan row**.

- Chart of accounts stays small and stable. Each `loan_product` declares four GL control
  accounts: principal receivable, interest receivable, interest income, penalty income
  (the last shared with the fees engine's fee_type setup). These accounts are snapshotted
  onto each `loan` row at disbursement.
- Every `journal_line` produced by a credit operation carries `sub_ledger_type='loan'`
  and `sub_ledger_id=loan.id`. A new compound index on `(sub_ledger_type, sub_ledger_id)`
  makes "all GL movement for loan X" an indexed query, not a table scan.
- The same columns are retrofitted onto `journal_lines` for savings
  (`sub_ledger_type='savings_account'`). This establishes one sub-ledger pattern
  across the system.
- The `loans` table carries a rich snapshot (see §3.3). The snapshot is updated
  atomically with the GL post inside a single DB transaction. Reads use the snapshot;
  accounting reports use GL aggregated by control account and sub_ledger_id.

### 2.2 Single-writer discipline

Every operation that changes a loan's financial state — disbursement, repayment,
interest accrual, penalty-event consumption, write-off — lives inside
`app/modules/credit/services/`. The pattern is identical for all:

```
SELECT loan FOR UPDATE
→ compute journal lines
→ LedgerService.post_journal_entry(...)  ← GL write
→ UPDATE loans SET snapshot_fields       ← snapshot write
→ audit_log entry
→ commit (one transaction)
```

No other code path may write to the snapshot columns. A CI ripgrep check enforces this:
`rg 'outstanding_principal|accrued_interest|accrued_penalties|total_paid_' --include='*.py'`
must find no matches outside `app/modules/credit/services/`.

### 2.3 Penalties — zero cross-module dependency

Late-payment penalties are `fee_type` rows with `applicable_to='loan'`,
`trigger_kind='schedule'`. The fees engine's schedule job asks the credit module:
"which loans are eligible for this penalty fee type?" via
`CreditQueryService.find_loans_eligible_for_fee(fee_type, as_of_date)`. This method
lives in the credit module and returns loan IDs plus the inputs the fees engine needs
(overdue principal, days past due).

The fees engine creates `fee_assessments` with `target_type='loan'`,
`target_id=loan.id`, and posts the GL entry tagged with `sub_ledger_type='loan'`.

The credit module subscribes to `FeeAssessmentCreated` and `FeeCollectionCreated`
outbox events where `target_type='loan'`. The consumer updates `loans.accrued_penalties`
(and `total_paid_penalties` for collections) in the locked+atomic pattern.

The authoritative penalty record is `fee_assessments WHERE target_type='loan'`.
There is no `loan_penalty_charges` table.

---

## 3. Data Model

### 3.1 `loan_products` table

One row per product type. Seeded at tenant provisioning.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `name` | TEXT NOT NULL | |
| `description` | TEXT nullable | |
| `interest_method` | TEXT NOT NULL | `flat \| reducing_balance` |
| `annual_interest_rate` | DECIMAL(19,4) NOT NULL | Annualised rate, e.g. `18.0000` = 18% |
| `repayment_frequency` | TEXT NOT NULL | `weekly \| biweekly \| monthly \| quarterly \| lump_sum` |
| `max_term_periods` | INT NOT NULL | Max number of repayment periods |
| `min_amount` | DECIMAL(19,4) NOT NULL | |
| `max_amount` | DECIMAL(19,4) NOT NULL | |
| `required_approvals` | INT NOT NULL DEFAULT 1 | Quorum for loan application approval |
| `disbursement_destinations` | TEXT[] NOT NULL | Allowed values: `member_savings`, `cash`, `internal_gl` |
| `repayment_allocation` | TEXT NOT NULL | `INTEREST_PRINCIPAL` (only valid value in v1) |
| `gl_principal_receivable_code` | TEXT NOT NULL | Control account — Dr on disbursement |
| `gl_interest_receivable_code` | TEXT NOT NULL | Control account — Dr when interest falls due |
| `gl_interest_income_code` | TEXT NOT NULL | Control account — Cr when interest is earned |
| `penalty_fee_type_code` | TEXT nullable | FK-by-code into `fee_types` for late penalty |
| `write_off_threshold` | DECIMAL(19,4) NOT NULL DEFAULT 0 | Write-offs above this require quorum=2 |
| `is_active` | BOOL NOT NULL DEFAULT true | |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

Auditable via `AuditableMixin`.

### 3.2 `loan_applications` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `loan_product_id` | UUID FK NOT NULL | |
| `member_id` | UUID FK NOT NULL | |
| `requested_amount` | DECIMAL(19,4) NOT NULL | |
| `requested_term_periods` | INT NOT NULL | |
| `purpose` | TEXT nullable | |
| `disbursement_destination` | TEXT NOT NULL | `member_savings \| cash \| internal_gl` |
| `disbursement_account_id` | UUID nullable | GL account id for `cash`/`internal_gl` destinations |
| `status` | TEXT NOT NULL | `draft \| submitted \| under_review \| approved \| rejected \| withdrawn` |
| `approval_request_id` | UUID nullable | FK to `approval_requests` |
| `approved_amount` | DECIMAL(19,4) nullable | May differ from requested |
| `approved_term_periods` | INT nullable | |
| `reviewed_by` | UUID nullable | actor who moved to under_review |
| `reviewed_at` | TIMESTAMPTZ nullable | |
| `decided_by` | UUID nullable | actor of final approve/reject |
| `decided_at` | TIMESTAMPTZ nullable | |
| `rejection_reason` | TEXT nullable | |
| `idempotency_key` | TEXT UNIQUE NOT NULL | |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

Auditable via `AuditableMixin`.

### 3.3 `loans` table

Created when an approved application is disbursed. Product terms are **snapshotted** at
this point — changes to the product never affect existing loans.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `loan_reference` | TEXT UNIQUE NOT NULL | Human-readable: `LN-{YYYYMM}-{6-digit seq}` |
| `loan_application_id` | UUID FK UNIQUE NOT NULL | |
| `loan_product_id` | UUID FK NOT NULL | Snapshot reference |
| `member_id` | UUID FK NOT NULL | |
| `status` | TEXT NOT NULL | See §4 |
| — **Snapshotted product terms** — | | |
| `principal_amount` | DECIMAL(19,4) NOT NULL | Disbursed amount |
| `interest_method` | TEXT NOT NULL | Snapshot |
| `annual_interest_rate` | DECIMAL(19,4) NOT NULL | Snapshot |
| `repayment_frequency` | TEXT NOT NULL | Snapshot |
| `term_periods` | INT NOT NULL | Number of installments |
| `repayment_allocation` | TEXT NOT NULL | Snapshot |
| `disbursement_destination` | TEXT NOT NULL | Snapshot |
| `disbursement_account_id` | UUID nullable | Snapshot |
| — **Snapshotted GL codes** — | | |
| `gl_principal_receivable_id` | UUID FK NOT NULL | Looked up from code at disbursement |
| `gl_interest_receivable_id` | UUID FK NOT NULL | |
| `gl_interest_income_id` | UUID FK NOT NULL | |
| `gl_disbursement_account_id` | UUID FK NOT NULL | Cash/savings account GL id |
| — **Balance snapshot** — | | |
| `outstanding_principal` | DECIMAL(19,4) NOT NULL DEFAULT 0 | |
| `accrued_interest` | DECIMAL(19,4) NOT NULL DEFAULT 0 | Earned, not yet paid |
| `accrued_penalties` | DECIMAL(19,4) NOT NULL DEFAULT 0 | Assessed, not yet paid |
| `total_paid_principal` | DECIMAL(19,4) NOT NULL DEFAULT 0 | Cumulative |
| `total_paid_interest` | DECIMAL(19,4) NOT NULL DEFAULT 0 | |
| `total_paid_penalties` | DECIMAL(19,4) NOT NULL DEFAULT 0 | |
| `total_written_off` | DECIMAL(19,4) NOT NULL DEFAULT 0 | |
| `last_repayment_at` | TIMESTAMPTZ nullable | |
| `last_repayment_amount` | DECIMAL(19,4) nullable | |
| — **Dates** — | | |
| `disbursed_at` | TIMESTAMPTZ nullable | Set when status → disbursed |
| `first_repayment_due` | DATE nullable | First installment due date |
| `maturity_date` | DATE nullable | Last installment due date |
| `closed_at` | TIMESTAMPTZ nullable | |
| `disbursed_by` | UUID NOT NULL | actor_id |
| `idempotency_key` | TEXT UNIQUE NOT NULL | |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

All DECIMAL fields NOT NULL DEFAULT 0. Auditable via `AuditableMixin`.

### 3.4 `loan_installments` table

Pre-computed amortisation schedule written at disbursement. Append-only.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `loan_id` | UUID FK NOT NULL | |
| `period_number` | INT NOT NULL | 1-based |
| `due_date` | DATE NOT NULL | |
| `principal_due` | DECIMAL(19,4) NOT NULL | |
| `interest_due` | DECIMAL(19,4) NOT NULL | |
| `total_due` | DECIMAL(19,4) NOT NULL | `principal_due + interest_due` |
| `principal_paid` | DECIMAL(19,4) NOT NULL DEFAULT 0 | |
| `interest_paid` | DECIMAL(19,4) NOT NULL DEFAULT 0 | |
| `status` | TEXT NOT NULL DEFAULT 'pending' | `pending \| partial \| paid \| overdue` |
| `paid_at` | TIMESTAMPTZ nullable | When fully paid |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

`UNIQUE (loan_id, period_number)`.

### 3.5 `loan_repayments` table

One row per capture. Append-only.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `loan_id` | UUID FK NOT NULL | |
| `amount` | DECIMAL(19,4) NOT NULL | Total received |
| `principal_applied` | DECIMAL(19,4) NOT NULL | |
| `interest_applied` | DECIMAL(19,4) NOT NULL | |
| `penalties_applied` | DECIMAL(19,4) NOT NULL DEFAULT 0 | |
| `overpayment` | DECIMAL(19,4) NOT NULL DEFAULT 0 | Excess above total owed |
| `payment_account_id` | UUID FK NOT NULL | GL account cash/savings was received from |
| `journal_entry_id` | UUID FK NOT NULL | |
| `posted_by` | UUID NOT NULL | |
| `narration` | TEXT nullable | |
| `idempotency_key` | TEXT UNIQUE NOT NULL | |
| `created_at` | TIMESTAMPTZ NOT NULL | |

### 3.6 `journal_lines` — schema addition

Add two columns to the existing `journal_lines` table (tenant schema migration):

```sql
sub_ledger_type  TEXT    -- 'loan' | 'savings_account' | null
sub_ledger_id    UUID    -- loan.id or savings_account.id | null
```

Index: `CREATE INDEX ON journal_lines (sub_ledger_type, sub_ledger_id) WHERE sub_ledger_id IS NOT NULL;`

The savings module is retrofitted at the same migration to populate these columns for new
journal lines it creates.

---

## 4. Loan Status Machine

```
draft → submitted → under_review → approved
                                       ↓
                                   disbursing → disbursed → in_arrears ─→ written_off
                                                     ↓
                                                   closed
              rejected ←────────────────────────────┤
              withdrawn ←──────────────────────────────┤
              cancelled ←──── (from draft/submitted)   │
```

| Transition | Trigger |
|-----------|---------|
| `draft → submitted` | Member/officer submits application |
| `submitted → under_review` | First approver acts |
| `under_review → approved` | Quorum met via ApprovalService |
| `under_review → rejected` | Rejected via ApprovalService |
| `* → withdrawn` | Member withdraws (before approved) |
| `draft/submitted → cancelled` | Officer cancels |
| `approved → disbursing` | Disbursement job starts (row locked) |
| `disbursing → disbursed` | GL posted, schedule written, snapshot set |
| `disbursed → in_arrears` | Arrears beat job: any overdue installment |
| `in_arrears → disbursed` | Arrears beat job: all overdue cleared |
| `disbursed/in_arrears → closed` | `outstanding_principal + accrued_interest + accrued_penalties == 0` |
| `disbursed/in_arrears/closed → written_off` | Write-off service (maker-checker) |

`in_arrears` is derived state — it is never set manually.

---

## 5. Interest Calculation

### 5.1 Flat method

Interest is computed once on the original principal:

```
total_interest = principal_amount × (annual_interest_rate / 100) × (term_periods / periods_per_year)
interest_per_period = total_interest / term_periods
principal_per_period = principal_amount / term_periods
```

Where `periods_per_year` is: `weekly=52, biweekly=26, monthly=12, quarterly=4, lump_sum=1`.

All installments carry the same `principal_due` and `interest_due`. Schedule is
generated at disbursement and never recalculated.

Interest income is recognised at disbursement: GL Dr Interest Receivable / Cr Interest
Income for `total_interest`. Repayments decrement Interest Receivable.

### 5.2 Reducing balance method

Each installment's interest is computed on the **outstanding principal at the start of
that period**:

```
period_rate = annual_interest_rate / 100 / periods_per_year

For each period i (1..term_periods):
    interest_i = outstanding_principal_i × period_rate
    principal_i = annuity_payment - interest_i
    outstanding_principal_{i+1} = outstanding_principal_i - principal_i
```

Where `annuity_payment` is solved via the standard annuity formula:
```
annuity_payment = P × r / (1 - (1+r)^-n)
```
(`P` = principal, `r` = period rate, `n` = term_periods).

Schedule is generated at disbursement. Interest income is recognised period-by-period:
a Celery beat job runs daily and posts `Dr Interest Receivable / Cr Interest Income` for
each installment whose `due_date <= today` that has not yet had interest accrued. This
is the `accrue_interest` beat task.

For flat method, interest is booked at disbursement (one-time GL entry). For reducing
balance, interest is accrued daily by the beat job.

---

## 6. Disbursement

### 6.1 Flow

```
LoanDisbursementService.disburse(loan_application_id, actor_id, idempotency_key)
  1. SELECT loan_application FOR UPDATE — verify status=approved
  2. Create loan record (status=disbursing)
  3. Compute amortisation schedule (_schedule.py pure functions)
  4. Resolve gl_disbursement_account_id (see §6.3 note)
  5. Post disbursement journal entry (see §6.2)
  6. Write loan_installments rows
  7. Set loan.outstanding_principal = principal_amount
  8. If flat method: post interest booking journal entry
  9. If member_savings destination: call SavingsService.record_external_credit(...)
  10. Set loan.status = disbursed, loan.disbursed_at = now()
  11. Commit — all of steps 2–10 in one DB transaction
```

Row lock at step 1 serialises concurrent disburse calls. The idempotency_key on the
`loans` table provides a secondary guard against duplicate execution.

### 6.2 Disbursement journal entries

**All destinations (principal):**
```
Dr  gl_principal_receivable_id  principal_amount
Cr  gl_disbursement_account_id  principal_amount
```

**Flat method (interest booking at disbursement):**
```
Dr  gl_interest_receivable_id   total_interest
Cr  gl_interest_income_id       total_interest
```

All lines tagged `sub_ledger_type='loan', sub_ledger_id=loan.id`.

**If destination = member_savings:**  
After the GL entry is committed, call
`SavingsService.record_external_credit(savings_account_id, amount, journal_entry_id,
source_module='credit', source_id=loan.id, narration='Loan disbursement')`.  
This writes a `savings_transactions` row with `transaction_type=EXTERNAL_CREDIT` but
does **not** post a new GL entry (GL was already posted by the credit module).

### 6.3 Disbursement destinations

| `disbursement_destination` | `disbursement_account_id` | Description |
|---|---|---|
| `member_savings` | null (resolved at disburse time) | Credited to member's primary savings account |
| `cash` | GL account id (asset, cash/bank type) | Teller cash payout |
| `internal_gl` | GL account id (any type) | Internal transfer, e.g. to a clearance account |

**`member_savings` GL resolution (step 4 in disbursement flow):** At disburse time,
resolve the member's primary savings account via `SavingsService.get_primary_account_for_member(member_id)`,
then look up that savings account's product to get `savings_product.liability_account_id`.
That becomes `loans.gl_disbursement_account_id` — the savings liability GL account that
is credited when the disbursement moves money into the member's savings. This ID is
snapshotted on the loan row at disbursement.

Product policy (`disbursement_destinations` array) restricts which destinations are
available at application time.

---

## 7. Repayment

### 7.1 Allocation policy

Interest-first (`INTEREST_PRINCIPAL`). Order within a repayment:

1. `accrued_interest` — clears first; any remaining accrued_interest is decremented
2. `outstanding_principal` — remainder after interest cleared
3. `accrued_penalties` — paid last (penalties are excess over principal+interest)

Any excess above `outstanding_principal + accrued_interest + accrued_penalties` is
recorded in `loan_repayments.overpayment` and flagged to the officer.

After allocation:
- Oldest unpaid/partially-paid installment(s) are updated (`principal_paid`,
  `interest_paid`, `status`) to reflect the payment.
- `loans` snapshot updated: `outstanding_principal`, `accrued_interest`,
  `total_paid_principal`, `total_paid_interest`, `last_repayment_at`,
  `last_repayment_amount`.

### 7.2 Repayment journal entry

```
Dr  payment_account_id          amount           (cash/savings received)
Cr  gl_principal_receivable_id  principal_applied
Cr  gl_interest_receivable_id   interest_applied
```

If `penalties_applied > 0`:
```
Cr  penalty_gl_account_id       penalties_applied   (from fee_type's gl_receivable_account)
```

All lines tagged `sub_ledger_type='loan', sub_ledger_id=loan.id`.

### 7.3 Savings-sourced repayments

If the payment comes from member's savings account:
- Credit module calls `SavingsService.record_external_debit(...)` after posting the GL
  entry, to write the savings statement row (`EXTERNAL_DEBIT`). No new GL from savings.

### 7.4 Loan closure

After each repayment, if `outstanding_principal + accrued_interest + accrued_penalties == 0`,
the loan transitions to `closed` and `closed_at` is set.

---

## 8. Beat Jobs

| Task | Schedule | Purpose |
|------|----------|---------|
| `accrue_reducing_balance_interest` | Daily | Post interest GL entry for reducing-balance loans with installments due today |
| `mark_loans_in_arrears` | Daily | Set `status=in_arrears` on loans with overdue installments; clear when resolved |
| `reconcile_loan_snapshots` | Daily (per tenant) | Compare snapshot fields to GL sums; emit structured alert + audit entry on mismatch |

The reconciliation job computes per loan:
```sql
SELECT
    SUM(debit_amount) FILTER (WHERE sub_ledger_type='loan' AND account_id=gl_principal_receivable_id) -
    SUM(credit_amount) FILTER (WHERE sub_ledger_type='loan' AND account_id=gl_principal_receivable_id)
    AS gl_outstanding_principal
FROM journal_lines jl
JOIN journal_entries je ON jl.journal_entry_id = je.id
WHERE jl.sub_ledger_id = <loan_id>
```
and compares to `loans.outstanding_principal`. Any drift → `loan_snapshot_drift` alert.

---

## 9. Write-Off

`LoanWriteOffService.write_off(loan_id, amount, reason, actor_id, idempotency_key)`:

- If `amount > loan_product.write_off_threshold`: requires maker-checker, quorum=2,
  routed through `ApprovalService` with executor `credit.write_off`.
- If `amount <= threshold`: direct execution.

Journal entry:
```
Dr  Loan Loss Expense account    amount
Cr  gl_principal_receivable_id   amount
```
Tagged with `sub_ledger_type='loan'`.

Snapshot: `outstanding_principal -= amount`, `total_written_off += amount`.  
Status → `written_off`.

---

## 10. API Endpoints

All routes require `X-Tenant-Slug` + `X-Actor-ID` headers.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/credit/products` | Create loan product |
| `GET` | `/credit/products` | List products |
| `GET` | `/credit/products/{id}` | Get product |
| `PATCH` | `/credit/products/{id}` | Update product (non-financial fields) |
| `POST` | `/credit/applications` | Submit loan application → 201 |
| `GET` | `/credit/applications` | List applications (filter by member, status) |
| `GET` | `/credit/applications/{id}` | Get application |
| `POST` | `/credit/applications/{id}/withdraw` | Member withdraws → 200 |
| `POST` | `/credit/applications/{id}/approve` | Approver approves (via ApprovalService) |
| `POST` | `/credit/applications/{id}/reject` | Approver rejects |
| `POST` | `/credit/loans/{application_id}/disburse` | Disburse approved application → 201 |
| `GET` | `/credit/loans` | List loans |
| `GET` | `/credit/loans/{id}` | Get loan + snapshot balance |
| `GET` | `/credit/loans/{id}/schedule` | Get installment schedule |
| `POST` | `/credit/loans/{id}/repayments` | Post repayment → 201 |
| `GET` | `/credit/loans/{id}/repayments` | List repayments |
| `POST` | `/credit/loans/{id}/write-off` | Submit write-off (maker-checker if above threshold) |
| `GET` | `/credit/query/loans-eligible-for-fee` | Internal: fees engine eligibility query |

---

## 11. Services Decomposition

```
app/modules/credit/
  __init__.py
  models.py          — LoanProduct, LoanApplication, Loan, LoanInstallment, LoanRepayment
  schemas.py         — Pydantic v2 request/response schemas
  api.py             — FastAPI router
  executors.py       — @approval_executor for 'credit.approve_application', 'credit.write_off'
  consumer.py        — Celery consumer: FeeAssessmentCreated, FeeCollectionCreated (target_type='loan')
  beat.py            — accrue_reducing_balance_interest, mark_loans_in_arrears, reconcile_loan_snapshots
  services/
    __init__.py
    product.py       — LoanProductService (CRUD)
    application.py   — LoanApplicationService (submit, withdraw, approve, reject)
    disbursement.py  — LoanDisbursementService (disburse, schedule generation)
    repayment.py     — LoanRepaymentService (apply_repayment, allocation engine)
    write_off.py     — LoanWriteOffService
    query.py         — CreditQueryService.find_loans_eligible_for_fee (read-only, used by fees engine)
    _schedule.py     — Schedule computation helpers (flat/reducing_balance); pure functions, no DB
```

---

## 12. Outbox Events Published

| Event | When | Payload |
|-------|------|---------|
| `LoanApplicationSubmitted` | Application submitted | `{application_id, member_id, amount}` |
| `LoanApplicationApproved` | Quorum met | `{application_id, loan_id, member_id}` |
| `LoanDisbursed` | Disbursement complete | `{loan_id, member_id, amount, destination}` |
| `LoanRepaymentPosted` | Repayment applied | `{loan_id, repayment_id, amount, outstanding_principal}` |
| `LoanClosed` | Loan reaches zero balance | `{loan_id, member_id}` |
| `LoanWrittenOff` | Write-off posted | `{loan_id, amount, reason}` |

---

## 13. Alembic Migration

Single tenant migration `010_credit_tables.py`:
- Add `sub_ledger_type` + `sub_ledger_id` + index to `journal_lines`
- Create `loan_products`, `loan_applications`, `loans`, `loan_installments`, `loan_repayments`
- Seed default loan product (optional; real products seeded by staff)

---

## 14. CLAUDE.md Additions

```markdown
## Credit module contracts (do not violate)
- Loan balance snapshot (loans.outstanding_principal, accrued_interest, accrued_penalties,
  total_paid_principal, total_paid_interest, total_paid_penalties, total_written_off) is
  the authoritative source for operational balance queries. GL is authoritative for
  accounting reports. The two are reconciled nightly by reconcile_loan_snapshots.
- All snapshot updates happen inside app/modules/credit/services/ in a single transaction
  with the matching GL post. No other code path may UPDATE the snapshot columns.
  CI enforces this with a ripgrep check.
- Every journal_line produced by a credit operation must carry sub_ledger_type='loan'
  and sub_ledger_id=loan.id. Lines without sub_ledger_id are not queryable in the
  loan sub-ledger.
- Loan penalties are fees. The authoritative penalty record is fee_assessments with
  target_type='loan'. The credit module snapshots accrued_penalties; it does not store
  penalty history. No loan_penalty_charges table.
- Loan write-off is the only operation that decreases outstanding_principal without a
  member payment. It requires maker-checker with quorum=2 above the product's
  write_off_threshold.
- SavingsService.record_external_credit and record_external_debit are the only permitted
  paths for the credit module to create savings transaction rows. Never call savings
  system_debit/system_credit from the credit module.
- CreditQueryService.find_loans_eligible_for_fee is the only cross-module interface
  the fees engine may call into the credit module. No other direct calls between modules.
```

---

## 15. Key Test Cases

- Flat schedule: verify `principal_per_period × n = principal`, `interest_per_period × n = total_interest`, GL balanced at disbursement
- Reducing balance schedule: verify annuity formula, each period's interest computed on declining balance, last period rounded correctly, GL balanced
- Interest-first allocation: repayment of 500 when accrued_interest=200, outstanding_principal=2000 → interest_applied=200, principal_applied=300
- Overpayment: repayment exceeds total owed → overpayment > 0, outstanding_principal = 0, loan transitions to closed
- Concurrent repayments: two simultaneous posts to same loan → row lock serializes, no lost updates, both committed correctly
- Snapshot reconciliation: inject a direct UPDATE to outstanding_principal bypassing the service → reconciliation job detects drift within one run
- Penalty event consumer: receive FeeAssessmentCreated with target_type='loan' → accrued_penalties incremented, idempotent on replay
- Write-off: above threshold creates approval_request, below threshold executes directly; GL entry balanced; snapshot updated; status=written_off
- sub_ledger query: all GL lines for a loan returned by `WHERE sub_ledger_type='loan' AND sub_ledger_id=loan.id` across disbursement + repayments + interest accrual
- Loan closure: after repayment that zeros the balance, status transitions to closed
- Disbursement to member_savings: savings_transactions row written with EXTERNAL_CREDIT, no duplicate GL entry
- Disbursement idempotency: disburse called twice with same idempotency_key → second call returns existing loan, no duplicate GL
