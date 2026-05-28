# Credit Module v1b — Design Spec
**Date:** 2026-05-28
**Status:** Approved for implementation
**Module:** `app/modules/credit/`
**Depends on:** credit v1a, core, ledger, members, savings, fees, maker_checker

---

## 1. Scope

Credit v1b extends the loan lifecycle established in v1a with five features:

**In scope:**
- Guarantors — hard lien on guarantor savings, explicit consent, proportional lien release
- Repayment schedule restructuring — term extension and payment holiday, maker-checker
- Bulk payroll-deduction repayments — CSV and JSON batch, maker-checker preview
- Loan statements — JSON API and PDF (WeasyPrint)
- Write-off recovery — partially reopens a written-off loan

**Out of scope (future):**
- External guarantors (non-members)
- Multiple concurrent active restructurings on the same loan
- Payroll integration via direct employer API
- Statement delivery (email, portal)

---

## 2. Architecture

### 2.1 Guarantor lien model

The platform uses a **separate lien table** (`loan_guarantor_liens`) rather than a
`frozen_amount` column on `savings_accounts`. This supports:
- A member guaranteeing multiple loans simultaneously (independent liens per loan)
- Proportional release as principal is repaid
- Full audit trail of lien changes

`SavingsService.get_available_balance(savings_account_id)` computes:
```
available = raw_balance - SUM(current_lien WHERE is_active=true AND savings_account_id=X)
```
Withdrawal submissions check `available_balance`, not `raw_balance`. The lien sum is
indexed on `savings_account_id` for O(active_liens) performance.

### 2.2 Schedule restructuring — supersede pattern

Restructuring never deletes installment rows. Unpaid installments are marked
`is_superseded=true` and a fresh set is written for the new schedule. Paid installments
are never touched. This preserves the original schedule for statement and audit purposes
while allowing the new schedule to coexist.

Each restructuring event is recorded in `loan_restructurings`. The `loan_installments`
table gains a `restructuring_id` FK (nullable) pointing to the restructuring event that
created the row.

### 2.3 Payroll batch — maker-checker preview

Payroll batches follow a validate-then-approve pattern:
1. Officer 1 submits batch (CSV or JSON) → system validates, creates `payroll_batch` +
   `payroll_batch_lines`, submits approval request
2. Officer 2 reviews the preview (matched/unmatched counts, total amount, line detail)
   and approves or rejects
3. On approval: executor applies each matched line via `LoanRepaymentService`

Each line is applied independently with its own idempotency key
(`batch_id:line_id`). A failed line records `status=error` and allows the rest
to continue — the batch is `applied` even with some error lines.

### 2.4 Write-off recovery

Recovery is the inverse of write-off: it credits `gl_principal_receivable` and debits
`gl_loan_loss_expense`, restoring `outstanding_principal`. The loan returns to
`in_arrears` (it was written off because it was delinquent). Guarantor liens are
reactivated proportionally to the restored outstanding principal.

Recovery does not require maker-checker — the authorizing event is the cash receipt
itself, which has already been through whatever payment verification the tenant uses.

### 2.5 Loan statement

Statement lines are assembled from:
- `journal_entries` / `journal_lines` tagged `sub_ledger_type='loan', sub_ledger_id=loan.id`
- `fee_assessments` / `fee_collections` where `target_type='loan', target_id=loan.id`

Each line carries a `running_balance` = outstanding principal at that point in time,
derived by replaying events in chronological order from disbursement.

PDF is rendered via **WeasyPrint** (HTML template → PDF). Justification: no existing
PDF library in the stack; WeasyPrint is the idiomatic Python HTML→PDF path and
produces bank-statement-quality output from a simple Jinja2 template.

---

## 3. Data Model

### 3.1 Changes to `loan_products`

```sql
ALTER TABLE loan_products
  ADD COLUMN required_guarantors INTEGER NOT NULL DEFAULT 0;

-- CHECK: required_guarantors >= 0
```

### 3.2 Changes to `loan_installments`

```sql
ALTER TABLE loan_installments
  ADD COLUMN restructuring_id UUID REFERENCES loan_restructurings(id),
  ADD COLUMN is_superseded    BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX ix_li_restructuring_id ON loan_installments (restructuring_id);
CREATE INDEX ix_li_loan_active ON loan_installments (loan_id) WHERE NOT is_superseded;
```

### 3.3 `loan_guarantors`

One row per guarantor nomination. Carries through from application to active loan.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `loan_application_id` | UUID FK NOT NULL | → `loan_applications.id` |
| `loan_id` | UUID FK nullable | Populated at disbursement |
| `guarantor_member_id` | UUID NOT NULL | Must be an active member (not the borrower) |
| `guaranteed_amount` | DECIMAL(19,4) NOT NULL | Snapshotted at nomination (`principal / required_guarantors`) |
| `status` | TEXT NOT NULL | `nominated \| accepted \| declined \| released` |
| `consented_at` | TIMESTAMPTZ nullable | Set when status → accepted |
| `released_at` | TIMESTAMPTZ nullable | Set when loan closes / writes off |
| `idempotency_key` | TEXT UNIQUE NOT NULL | |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

Constraints:
- `CHECK (status IN ('nominated', 'accepted', 'declined', 'released'))`
- `UNIQUE (loan_application_id, guarantor_member_id)` — no duplicate nominations
- `INDEX (loan_application_id)`, `INDEX (guarantor_member_id)`

### 3.4 `loan_guarantor_liens`

Tracks the live lien against each guarantor's savings account. One row per
guarantor-loan pair. A member guaranteeing N loans has N rows.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `loan_guarantor_id` | UUID FK NOT NULL | → `loan_guarantors.id` |
| `savings_account_id` | UUID NOT NULL | Guarantor's primary savings account |
| `original_lien` | DECIMAL(19,4) NOT NULL | Amount frozen at disbursement |
| `current_lien` | DECIMAL(19,4) NOT NULL | Reduces proportionally with repayments |
| `is_active` | BOOL NOT NULL DEFAULT true | False when loan closes / writes off |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

Constraints:
- `CHECK (original_lien > 0)`, `CHECK (current_lien >= 0)`
- `INDEX (savings_account_id, is_active)` — used by available-balance query
- `INDEX (loan_guarantor_id)`

### 3.5 `loan_restructurings`

One row per executed restructuring event. Append-only.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `loan_id` | UUID FK NOT NULL | → `loans.id` |
| `restructuring_type` | TEXT NOT NULL | `term_extension \| payment_holiday` |
| `periods_added` | INT NOT NULL | Periods extended or skipped (≥ 1) |
| `new_term_periods` | INT NOT NULL | Total loan term after restructuring |
| `new_maturity_date` | DATE NOT NULL | |
| `reason` | TEXT NOT NULL | |
| `approval_request_id` | UUID nullable | FK to `approval_requests` |
| `executed_by` | UUID NOT NULL | Actor who triggered execution |
| `executed_at` | TIMESTAMPTZ NOT NULL | |
| `idempotency_key` | TEXT UNIQUE NOT NULL | |
| `created_at` | TIMESTAMPTZ NOT NULL | |

Constraints:
- `CHECK (restructuring_type IN ('term_extension', 'payment_holiday'))`
- `CHECK (periods_added >= 1)`
- `INDEX (loan_id)`

### 3.6 `payroll_batches`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `reference` | TEXT UNIQUE NOT NULL | Human-readable: `PAY-{YYYYMM}-{seq}` |
| `status` | TEXT NOT NULL | `pending_review \| approved \| rejected \| applied` |
| `submitted_by` | UUID NOT NULL | |
| `approved_by` | UUID nullable | |
| `approval_request_id` | UUID nullable | |
| `total_rows` | INT NOT NULL | All rows in the batch |
| `matched_rows` | INT NOT NULL | Rows with a valid loan + amount |
| `unmatched_rows` | INT NOT NULL | |
| `total_amount` | DECIMAL(19,4) NOT NULL | Sum of matched amounts |
| `source_format` | TEXT NOT NULL | `csv \| json` |
| `idempotency_key` | TEXT UNIQUE NOT NULL | |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

Constraints:
- `CHECK (status IN ('pending_review', 'approved', 'rejected', 'applied'))`
- `CHECK (source_format IN ('csv', 'json'))`

### 3.7 `payroll_batch_lines`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `payroll_batch_id` | UUID FK NOT NULL | → `payroll_batches.id` |
| `member_id` | UUID nullable | Null if member not found |
| `raw_member_ref` | TEXT NOT NULL | Member ID or ref string as provided |
| `amount` | DECIMAL(19,4) NOT NULL | |
| `loan_id` | UUID nullable | Active loan found for member |
| `status` | TEXT NOT NULL | `matched \| unmatched \| applied \| error` |
| `error_reason` | TEXT nullable | |
| `repayment_id` | UUID nullable | Populated after successful apply |
| `created_at` | TIMESTAMPTZ NOT NULL | |

Constraints:
- `CHECK (status IN ('matched', 'unmatched', 'applied', 'error'))`
- `CHECK (amount > 0)`
- `INDEX (payroll_batch_id)`, `INDEX (loan_id)`

---

## 4. Loan Status Machine — Additions

New transition added to v1a status machine:

| Transition | Trigger |
|-----------|---------|
| `written_off → in_arrears` | `LoanWriteOffService.recover()` — recovery posted |

The loan re-enters `in_arrears` after recovery (it was written off because it was
delinquent; the daily `mark_loans_in_arrears` beat job will correct it to `disbursed`
if all installments are current after recovery).

---

## 5. Guarantor Flows

### 5.1 Nomination

`GuarantorService.nominate(application_id, guarantor_member_ids, actor_id)`:
- Validates: application must be in `submitted` status; `len(ids) == product.required_guarantors`;
  no guarantor is the borrower; no duplicates; all guarantor members are active
- If `product.required_guarantors == 0`: raises `ValueError` (nomination not applicable)
- Creates one `loan_guarantors` row per guarantor with `status=nominated`
- Publishes `GuarantorNominated` outbox event per guarantor

### 5.2 Consent gate

`LoanApplicationService` blocks the transition to officer approval if
`product.required_guarantors > 0` AND any `loan_guarantors` row for the application
has `status NOT IN ('accepted')`. When `required_guarantors == 0`, the consent gate
is skipped entirely. All required guarantors must be `accepted` before the application
is eligible for approval.

### 5.3 Accept / Decline

`GuarantorService.accept(loan_guarantor_id, actor_id)`:
- Resolves the `member_id` linked to the acting `tenant_user` (via `TenantUserService.get_member_id(actor_id)`);
  that `member_id` must match `loan_guarantors.guarantor_member_id` — a guarantor can only consent for themselves
- Sets `status=accepted`, `consented_at=now()`
- Publishes `GuarantorAccepted`

`GuarantorService.decline(loan_guarantor_id, actor_id)`:
- Same actor-member validation as accept
- Sets `status=declined`
- Application remains in `submitted`; borrower/officer must nominate a replacement
- Publishes `GuarantorDeclined`

### 5.4 Lien placement (at disbursement)

Called by `LoanDisbursementService` after GL post, within the same transaction.
No-op when `product.required_guarantors == 0`.

```python
GuarantorService.place_liens(loan, session):
    guarantors = accepted_guarantors(loan.loan_application_id)
    if not guarantors:
        return   # product requires no guarantors
    lien_share = loan.principal_amount / len(guarantors)
    for guarantor in guarantors:
        savings_acct = SavingsService.get_primary_account_for_member(
            guarantor.guarantor_member_id
        )
        guarantor.loan_id = loan.id
        create loan_guarantor_liens(
            loan_guarantor_id=guarantor.id,
            savings_account_id=savings_acct.id,
            original_lien=lien_share,
            current_lien=lien_share,
            is_active=True,
        )
```

### 5.5 Proportional lien release (after each repayment)

Called by `LoanRepaymentService` after snapshot update, within the same transaction:

```python
GuarantorService.adjust_liens(loan, principal_applied, session):
    repayment_fraction = principal_applied / loan.principal_amount
    for lien in active_liens(loan.id):
        reduction = lien.original_lien * repayment_fraction
        lien.current_lien = max(Decimal("0"), lien.current_lien - reduction)
```

### 5.6 Full release (loan closure or write-off)

Called by repayment service (on closure) and write-off service:

```python
GuarantorService.release_liens(loan_id, session):
    for lien in active_liens(loan_id):
        lien.is_active = False
        lien.current_lien = Decimal("0")
    for guarantor in guarantors(loan_id):
        guarantor.status = "released"
        guarantor.released_at = now()
```

### 5.7 Lien reactivation (on write-off recovery)

Called by `LoanWriteOffService.recover()`:

```python
GuarantorService.reactivate_liens(loan, restored_amount, session):
    for guarantor in released_guarantors(loan_id):
        guarantor.status = "accepted"   # reactivate
        guarantor.released_at = None
        lien_share = restored_amount / count(guarantors)
        lien.current_lien = lien_share
        lien.is_active = True
```

---

## 6. Schedule Restructuring Flow

```
LoanRestructuringService.restructure(
    loan_id, restructuring_type, periods_added, reason, actor_id, idempotency_key
)
  → validates: loan must be disbursed or in_arrears; periods_added >= 1
  → submits ApprovalService.submit(
        operation_type='credit.restructure_schedule',
        payload={loan_id, restructuring_type, periods_added, reason, idempotency_key},
        required_approvals=2
    )
  → returns {approval_request_id}
```

**Executor `credit.restructure_schedule`:**

```
_execute_restructuring(loan_id, restructuring_type, periods_added, reason, ...):
  1. SELECT loan FOR UPDATE
  2. SELECT loan_installments WHERE loan_id=X AND NOT is_superseded ORDER BY period_number
  3. Identify last paid period (status='paid') → last_paid_period_number
  4. Mark all periods > last_paid_period_number as is_superseded=true
  5. Compute new schedule from outstanding_principal at restructuring date:
       - term_extension: n_remaining = (term_periods - last_paid_period_number) + periods_added
         Recompute installments from period (last_paid_period_number + 1) using outstanding_principal
       - payment_holiday: shift due_dates of next periods_added installments out by periods_added
         periods; then continue normally (no interest waiver — interest continues to accrue)
  6. Write new loan_installments rows with restructuring_id=restructuring.id
  7. Create loan_restructurings row (executed_at=now())
  8. Update loan.term_periods = new_term_periods, loan.maturity_date = new_maturity_date
  9. Audit log entry
  10. Publish LoanRestructured outbox event
  11. Commit
```

Interest method is unchanged. For reducing balance, new installments use `outstanding_principal`
as the new principal and remaining periods for the annuity formula. For flat, remaining
unearned interest is spread evenly across new periods.

---

## 7. Bulk Payroll Repayments Flow

### 7.1 Submit

```
POST /credit/payroll-batches
  Content-Type: multipart/form-data  (CSV)
  Content-Type: application/json     (JSON)

PayrollBatchService.submit_batch(raw_input, source_format, actor_id, idempotency_key):
  1. Parse input:
       CSV: rows of {member_id, amount}
       JSON: [{member_id, amount}, ...]
  2. For each row:
       - Look up member by member_id (UUID or member_number)
       - If not found: status=unmatched, error_reason='member_not_found'
       - If found: find active loan (status IN ('disbursed', 'in_arrears'))
       - If no active loan: status=unmatched, error_reason='no_active_loan'
       - Else: status=matched, loan_id=loan.id
  3. Create payroll_batch row (status=pending_review)
  4. Create payroll_batch_lines rows
  5. Submit approval_request (credit.apply_payroll_batch, quorum=1)
  6. Return PayrollBatchPreviewOut (batch_id, matched, unmatched, lines)
```

### 7.2 Apply (executor)

```
credit.apply_payroll_batch executor:
  PayrollBatchService.apply_batch(batch_id, actor_id):
    batch = SELECT payroll_batch FOR UPDATE WHERE id=X AND status='approved'
    for line in matched_lines(batch_id):
        idem_key = f"payroll-{batch_id}-{line.id}"
        try:
            LoanRepaymentService.apply_repayment(
                loan_id=line.loan_id,
                amount=line.amount,
                payment_account_id=<payroll_clearing_account_id>,
                posted_by=actor_id,
                idempotency_key=idem_key,
                narration=f"Payroll deduction batch {batch.reference}",
            )
            line.status = 'applied'
            line.repayment_id = repayment.id
        except Exception as e:
            line.status = 'error'
            line.error_reason = str(e)
        await session.commit()   ← per-line commit; partial success is OK
    batch.status = 'applied'
    Publish PayrollBatchApplied event
```

The payroll clearing account (a liability GL account) is passed in the batch submission
request as `clearing_account_id` (a GL account UUID). The caller is responsible for
providing the correct account — typically a "Payroll Deductions Payable" liability account
set up in the tenant's chart of accounts.

---

## 8. Write-Off Recovery Flow

```
LoanWriteOffService.recover(
    loan_id, amount, reason, actor_id, idempotency_key
):
  idem_key = f"loan-wor-{idempotency_key}"
  Guard: check for existing journal entry with idem_key (idempotency)

  1. SELECT loan FOR UPDATE — must be status='written_off'
  2. amount must be > 0 and <= loan.total_written_off
  3. GL entry (same transaction):
       Dr  gl_principal_receivable_id   amount    (sub_ledger_type='loan', sub_ledger_id=loan.id)
       Cr  gl_loan_loss_expense_id      amount
  4. loan.total_written_off -= amount
  5. loan.outstanding_principal += amount
  6. loan.status = 'in_arrears'
  7. GuarantorService.reactivate_liens(loan, amount, session)
  8. Audit log (before: written_off, after: in_arrears + new snapshot)
  9. Publish LoanRecoveryPosted outbox event
  10. Commit
```

No maker-checker required. The cash receipt is the authorizing event.

---

## 9. Loan Statement

### 9.1 JSON

```
GET /credit/loans/{id}/statement?from=YYYY-MM-DD&to=YYYY-MM-DD

LoanStatementService.get_statement(loan_id, from_date, to_date) → list[StatementLine]
```

Statement lines assembled from (ordered by `posted_at` / `created_at`):

| Source | Line type | Debit | Credit |
|--------|-----------|-------|--------|
| Disbursement journal entry | Disbursement | — | principal_amount |
| Flat interest booking | Interest booked | — | total_interest |
| Interest accrual journal entry | Interest accrual | — | period_interest |
| `loan_repayments` row | Repayment | amount | — |
| `fee_assessments` (target=loan) | Penalty assessed | penalty_amount | — |
| Write-off journal entry | Write-off | — | amount |
| Recovery journal entry | Recovery | amount | — |

Each line: `{date, type, description, debit, credit, running_balance}`.  
`running_balance` is computed by replaying entries in chronological order starting from 0
at disbursement, where debits reduce and credits increase the balance (from the member's
perspective: money owed).

Date filter applies to `posted_at`. If `from` / `to` are omitted, the full loan history
is returned.

### 9.2 PDF

```
GET /credit/loans/{id}/statement.pdf?from=YYYY-MM-DD&to=YYYY-MM-DD
```

`LoanStatementService.render_pdf(loan_id, from_date, to_date) → bytes`

Flow:
1. Call `get_statement()` to get lines
2. Load loan + member details
3. Render Jinja2 HTML template (`templates/credit/loan_statement.html`)
4. Convert to PDF via `weasyprint.HTML(string=html).write_pdf()`
5. Return bytes with `Content-Type: application/pdf`

Template lives at `app/modules/credit/templates/loan_statement.html`.
WeasyPrint is added as a new dependency (`weasyprint>=62.0`).

---

## 10. API Endpoints

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| `POST` | `/credit/applications/{id}/guarantors` | Nominate guarantors (list of member IDs) | 201 |
| `GET` | `/credit/applications/{id}/guarantors` | List guarantors + consent status | 200 |
| `POST` | `/credit/guarantors/{id}/accept` | Guarantor accepts nomination | 200 |
| `POST` | `/credit/guarantors/{id}/decline` | Guarantor declines nomination | 200 |
| `POST` | `/credit/loans/{id}/restructure` | Submit restructuring → approval | 202 |
| `GET` | `/credit/loans/{id}/restructurings` | List restructuring history | 200 |
| `POST` | `/credit/payroll-batches` | Submit batch (CSV or JSON) | 201 |
| `GET` | `/credit/payroll-batches/{id}` | Get batch status + line summary | 200 |
| `POST` | `/credit/payroll-batches/{id}/approve` | Approve batch → apply | 200 |
| `POST` | `/credit/payroll-batches/{id}/reject` | Reject batch | 200 |
| `POST` | `/credit/loans/{id}/recover` | Post write-off recovery | 201 |
| `GET` | `/credit/loans/{id}/statement` | JSON loan statement | 200 |
| `GET` | `/credit/loans/{id}/statement.pdf` | PDF loan statement | 200 (application/pdf) |

---

## 11. Services Decomposition

```
app/modules/credit/
  services/
    guarantor.py          GuarantorService
                            nominate(application_id, member_ids, actor_id)
                            accept(loan_guarantor_id, actor_id)
                            decline(loan_guarantor_id, actor_id)
                            place_liens(loan, session)
                            release_liens(loan_id, session)
                            adjust_liens(loan, principal_applied, session)
                            reactivate_liens(loan, restored_amount, session)

    restructuring.py      LoanRestructuringService
                            restructure(loan_id, type, periods_added, reason,
                                        actor_id, idempotency_key)
                            _execute_restructuring(payload, session)

    payroll.py            PayrollBatchService
                            submit_batch(raw_input, source_format, actor_id,
                                         idempotency_key, clearing_account_id)
                            _parse_csv(file_bytes) → list[RawRow]
                            _parse_json(data) → list[RawRow]
                            _match_rows(raw_rows, session) → list[MatchedRow]
                            apply_batch(batch_id, actor_id)

    statement.py          LoanStatementService
                            get_statement(loan_id, from_date, to_date)
                              → list[StatementLine]
                            render_pdf(loan_id, from_date, to_date) → bytes

Modified:
    disbursement.py       Calls GuarantorService.place_liens() after GL post
    repayment.py          Calls GuarantorService.adjust_liens() after snapshot update;
                          calls release_liens() on loan closure
    write_off.py          Calls GuarantorService.release_liens() on write-off;
                          adds recover() method

New executors (added to executors.py):
    credit.restructure_schedule  → LoanRestructuringService._execute_restructuring()
    credit.apply_payroll_batch   → PayrollBatchService.apply_batch()
```

---

## 12. Outbox Events Published

| Event | When | Payload |
|-------|------|---------|
| `GuarantorNominated` | Guarantor nominated on application | `{application_id, guarantor_member_id}` |
| `GuarantorAccepted` | Guarantor consents | `{loan_guarantor_id, application_id, guarantor_member_id}` |
| `GuarantorDeclined` | Guarantor declines | `{loan_guarantor_id, application_id, guarantor_member_id}` |
| `LoanRestructured` | Restructuring executed | `{loan_id, restructuring_id, type, periods_added}` |
| `PayrollBatchApplied` | All batch lines processed | `{batch_id, applied_count, error_count, total_amount}` |
| `LoanRecoveryPosted` | Write-off recovery posted | `{loan_id, amount, journal_entry_id}` |

---

## 13. Alembic Migration

Single tenant migration `011_credit_v1b_tables.py`:

```sql
-- Changes to existing tables
ALTER TABLE loan_products ADD COLUMN required_guarantors INTEGER NOT NULL DEFAULT 0;
ALTER TABLE loan_installments
  ADD COLUMN restructuring_id UUID REFERENCES loan_restructurings(id),
  ADD COLUMN is_superseded BOOLEAN NOT NULL DEFAULT false;

-- New tables (in dependency order)
CREATE TABLE loan_guarantors (...);
CREATE TABLE loan_guarantor_liens (...);
CREATE TABLE loan_restructurings (...);
ALTER TABLE loan_installments ADD CONSTRAINT fk_li_restructuring
  FOREIGN KEY (restructuring_id) REFERENCES loan_restructurings(id);

-- Payroll tables
CREATE TABLE payroll_batches (...);
CREATE TABLE payroll_batch_lines (...);

-- Sequences
CREATE SEQUENCE IF NOT EXISTS payroll_batch_number_seq START 1;
```

Note: `loan_restructurings` must be created before the FK is added to
`loan_installments`.

---

## 14. CLAUDE.md Additions

```markdown
## Credit module v1b contracts (do not violate)
- Guarantor lien balance is always computed as SUM(current_lien WHERE is_active=true)
  from loan_guarantor_liens. Never cache this value outside a transaction.
- SavingsService.get_available_balance() must always subtract active liens before
  returning a withdrawable balance. Never bypass this for guarantors.
- Lien mutations (place, adjust, release, reactivate) must happen in the same
  DB transaction as the triggering financial operation (disbursement, repayment, write-off,
  recovery). Never update liens in a separate transaction.
- Payroll batch lines are applied one per commit. A failed line records status=error
  and does NOT roll back successfully applied lines.
- Restructuring never deletes installment rows. Mark is_superseded=true and write new rows.
- Write-off recovery does not require maker-checker. The cash receipt is the authorizing event.
- WeasyPrint is the only permitted PDF renderer in this module. Do not add alternative
  PDF libraries.
```

---

## 15. Key Test Cases

### Guarantors
- Nominate guarantors — creates loan_guarantors rows with status=nominated
- Application cannot be approved while any guarantor is in nominated/declined status
- Guarantor accepts → status=accepted; all accepted → application eligible for approval
- Guarantor declines → application stays in submitted; replacement can be nominated
- Disbursement creates loan_guarantor_liens with current_lien = principal / required_guarantors
- After repayment: current_lien reduced proportionally; SUM(current_lien) < original
- After loan closure: all liens is_active=false, all guarantors status=released
- Available balance excludes current_lien; guarantor cannot withdraw frozen amount

### Schedule Restructuring
- Term extension: original unpaid installments superseded; new installments written with correct period numbers; loan.maturity_date updated
- Payment holiday: due dates of next N installments shifted; loan.term_periods and maturity_date updated
- Restructuring requires quorum=2 — direct execution raises ValueError
- Multiple restructurings on same loan: each creates a loan_restructurings row; prior superseded installments stay superseded
- Paid installments are never superseded regardless of restructuring type

### Payroll Batches
- CSV upload: parsed correctly; matched/unmatched counts correct
- JSON submit: equivalent to CSV
- Unmatched rows (no loan, member not found): flagged, not applied
- Batch requires approval; applying before approval raises ValueError
- After approval: all matched lines applied; each has its own repayment_id
- Failed line: status=error; other lines still applied; batch still reaches status=applied
- Idempotency: applying same batch twice → second apply is no-op for already-applied lines

### Write-Off Recovery
- Recovery on active loan raises ValueError (must be written_off)
- Recovery > total_written_off raises ValueError
- GL: Dr principal_receivable / Cr loan_loss_expense — balanced
- outstanding_principal restored, total_written_off reduced, status → in_arrears
- Guarantor liens reactivated with correct current_lien values
- Recovery idempotent: same idempotency_key twice → no duplicate GL entry

### Loan Statement
- Statement lines in chronological order; running_balance correct after each event
- Date filter: only lines within from/to range returned
- PDF endpoint returns bytes with Content-Type: application/pdf
- Empty period: empty lines list, correct loan header
```
