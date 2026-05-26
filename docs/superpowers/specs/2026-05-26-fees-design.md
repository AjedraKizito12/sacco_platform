# Fees Module — Design Spec
**Date:** 2026-05-26  
**Status:** Approved for implementation  
**Module:** `app/modules/fees/`  
**Depends on:** core, platform_, iam, ledger, members, savings

---

## 1. Why a Fee Engine (Not Hardcoded Fee Types)

The fees module is a **general-purpose fee engine**, not a hardcoded membership + annual subscription module. This is the right level of generality even for v1 because:

- Fees appear across every future module: loan processing, late-payment penalties, NSF returns, share certificate issuance, account closure, dormancy, insurance premiums. Each is structurally identical — a fee type, a trigger, a GL mapping, an assessment event, a collection event.
- Building for only membership + annual means rebuilding the same shape four more times and then refactoring into an engine. The engine costs ~20% more code now and prevents a rewrite.
- Within v1 scope alone, membership (event-triggered) and annual subscription (schedule-triggered) are already two distinct trigger mechanisms. The engine expresses both cleanly without two unrelated code paths.

**What C (the engine) means in practice:** a `fee_types` table seeded with today's fee types; new rows when new modules ship. The data model is barely different from a hardcoded approach — the difference is that fee types are data, not code.

---

## 2. Data Model

### 2.1 `fee_types` table

The fee catalog. One row per fee type. Seeded at tenant provisioning; new rows added as modules ship.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `code` | TEXT UNIQUE NOT NULL | Machine identifier: `MEMBERSHIP`, `ANNUAL_SUB`, `LOAN_PROCESSING`, … |
| `name` | TEXT NOT NULL | Display name |
| `description` | TEXT nullable | |
| `applicable_to` | TEXT NOT NULL | Enum: `member \| savings_account \| loan \| share_account` |
| `amount_kind` | TEXT NOT NULL | Enum: `fixed \| percentage \| tiered`. **Only `fixed` is executed in v1**; column exists for future use |
| `amount` | DECIMAL(19,4) NOT NULL | For `fixed` fees |
| `percentage_basis` | TEXT nullable | For `percentage` fees — deferred v2 |
| `percentage_rate` | DECIMAL(19,4) nullable | For `percentage` fees — deferred v2 |
| `currency` | TEXT NOT NULL | e.g. `UGX` |
| `trigger_kind` | TEXT NOT NULL | Enum: `event \| schedule \| manual` |
| `event_name` | TEXT nullable | For `event` triggers: e.g. `MemberActivated` |
| `schedule_config` | JSONB nullable | For `schedule` triggers: `{anchor: "tenant_financial_year_start", recurrence: "yearly"}` |
| `gl_income_account_code` | TEXT NOT NULL | GL account code for fee income (Cr on assessment) |
| `gl_receivable_account_code` | TEXT NOT NULL | GL account code for fee receivable (Dr on assessment) |
| `is_active` | BOOL NOT NULL DEFAULT true | |
| `requires_collection` | BOOL NOT NULL | `true` = attempt auto-collection from savings after assessment. `false` = assessment creates receivable; teller collects manually |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

Auditable via `AuditableMixin`.

**Constraints:**
- `CHECK(amount_kind IN ('fixed', 'percentage', 'tiered'))`
- `CHECK(trigger_kind IN ('event', 'schedule', 'manual'))`
- `CHECK(applicable_to IN ('member', 'savings_account', 'loan', 'share_account'))`
- `CHECK(amount >= 0)`
- Index on `(is_active, trigger_kind)` for the beat task query.
- Index on `(is_active, event_name)` for the event consumer query.

### 2.2 `fee_assessments` table

One row per (fee type, target entity, period). Assessment = "this fee is owed."

Uses `AuditableMixin` because status transitions (`assessed → paid`, etc.) are meaningful business state changes that must be audited. Unlike pure financial tables (e.g., `savings_transactions`, `journal_lines`) where the row is never mutated, the assessment row is the receivable record and its lifecycle changes are the authoritative history.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `fee_type_id` | UUID FK → `fee_types.id` NOT NULL | |
| `target_type` | TEXT NOT NULL | Same enum as `applicable_to` |
| `target_id` | UUID NOT NULL | Polymorphic FK to the target entity |
| `period_start` | DATE NOT NULL | Start of the fee period; for one-shot fees = assessment date |
| `period_end` | DATE nullable | End of period. NULL for one-shot fees |
| `amount` | DECIMAL(19,4) NOT NULL | **Snapshotted** from `fee_type.amount` at assessment time. Changing `fee_type.amount` never retroactively changes this |
| `currency` | TEXT NOT NULL | Snapshotted |
| `status` | TEXT NOT NULL DEFAULT `assessed` | Enum: `assessed \| partially_paid \| paid \| waived \| cancelled` |
| `assessed_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| `due_at` | TIMESTAMPTZ nullable | Payment due date |
| `paid_at` | TIMESTAMPTZ nullable | Set when status transitions to `paid` |
| `waived_by` | UUID nullable | FK to tenant_users (no FK constraint — cross-module). Set when waived |
| `waiver_reason` | TEXT nullable | |
| `journal_entry_id` | UUID FK → `journal_entries.id` NOT NULL | Assessment GL entry |
| `triggered_by_event_id` | UUID nullable | Outbox event UUID that triggered assessment (for event-triggered fees) |
| `created_at` | TIMESTAMPTZ NOT NULL | |
| `updated_at` | TIMESTAMPTZ NOT NULL | |

Auditable via `AuditableMixin`.

**Constraints:**
- `UNIQUE(fee_type_id, target_type, target_id, period_start)` — **idempotency key**. Prevents double-assessment for same fee/target/period.
- `CHECK(status IN ('assessed', 'partially_paid', 'paid', 'waived', 'cancelled'))`
- `CHECK(amount > 0)`
- Index on `(status)` for retry task.
- Index on `(target_type, target_id)` for member statement queries.
- Index on `(fee_type_id, status)` for collection queries.

### 2.3 `fee_collections` table

One row per payment toward an assessment. A single assessment can have multiple collection rows (partial payments). **Append-only.**

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `fee_assessment_id` | UUID FK → `fee_assessments.id` NOT NULL | |
| `amount` | DECIMAL(19,4) NOT NULL | Amount collected in this row |
| `collected_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| `method` | TEXT NOT NULL | Enum: `savings_deduction \| cash \| journal_voucher` |
| `collected_by` | UUID NOT NULL | FK to tenant_users (no FK constraint — cross-module) |
| `journal_entry_id` | UUID FK → `journal_entries.id` NOT NULL | Collection GL entry |
| `idempotency_key` | TEXT NOT NULL UNIQUE | |
| `source_module` | TEXT NOT NULL DEFAULT `fees` | |
| `source_id` | UUID NOT NULL | = `fee_assessment_id` |
| `created_at` | TIMESTAMPTZ NOT NULL | |

Auditable via `AuditableMixin`.

**Constraints:**
- `CHECK(amount > 0)`
- `CHECK(method IN ('savings_deduction', 'cash', 'journal_voucher'))`
- `UNIQUE(idempotency_key)`

---

## 3. Savings Module Extension: `system_debit` / `system_credit`

A prerequisite for auto-collection. The savings module gains two new service methods callable only by other service modules (not from API routes).

### 3.1 Why not skip `savings_transactions`

Option A (post GL directly, skip savings_transactions) violates the spirit of the boundary rule:

1. **Member statements break.** Deposits and withdrawals appear in `savings_transactions`. Fee deductions posted only to GL would be invisible to `GET /savings/{id}/transactions` unless a second GL-search path is added. Two code paths for "what happened to this account" means bugs.
2. **Search is incomplete.** `savings_transactions` is the Elasticsearch index source. Fee deductions skipping that table are invisible to member transaction search.
3. **Balance derivation is wrong.** Balance is derived from `savings_transactions`. A fee deduction posting only to GL would make balance appear higher than reality.

Option B (add `system_debit` to SavingsService) is correct: the savings module owns the savings ledger; every change — regardless of initiator — produces a `savings_transactions` row.

### 3.2 Schema changes to `savings_transactions`

Add three new columns and extend one existing constraint:

| Column | Type | Notes |
|--------|------|-------|
| `transaction_type` | TEXT (existing) | Extend CHECK to add `SYSTEM_DEBIT`, `SYSTEM_CREDIT` alongside existing `deposit`, `withdrawal` |
| `source_module` | TEXT nullable (new) | `fees`, `credit`, etc. NULL for user-initiated transactions |
| `source_id` | UUID nullable (new) | Originating record ID (e.g., `fee_assessment.id`). NULL for user-initiated |
| `reason` | TEXT nullable (new) | Enum: `FEE_COLLECTION \| LOAN_REPAYMENT \| LOAN_DISBURSEMENT \| REFUND \| RECEIVABLE_RECOVERY`. NULL for user-initiated |

**Rule:** Every system-initiated row (`source_module IS NOT NULL`) MUST have `source_id` populated. Reconstructing why a deduction happened must be possible from the row alone.

### 3.3 `SavingsService.system_debit()` signature

```python
async def system_debit(
    self,
    *,
    savings_account_id: uuid.UUID,
    amount: Decimal,
    reason: str,               # FEE_COLLECTION | LOAN_REPAYMENT | ...
    source_module: str,        # 'fees' | 'credit' | ...
    source_id: uuid.UUID,      # originating record ID
    actor: uuid.UUID,          # system actor UUID (nil UUID for automated)
    idempotency_key: str,
    narration: str | None = None,
    on_insufficient_funds: str = "fail",  # 'fail' | 'partial' | 'allow_negative'
) -> SystemDebitResult
```

**`SystemDebitResult`** (Pydantic model or dataclass):
```python
@dataclass
class SystemDebitResult:
    transaction_id: uuid.UUID
    debited_amount: Decimal
    requested_amount: Decimal
    shortfall_amount: Decimal  # 0 if fully debited
    status: str                # 'full' | 'partial' | 'zero' (for 'partial' on zero balance)
```

**`on_insufficient_funds` behaviour:**
- `fail` (default): raises `ValueError` if `current_balance < amount`. No rows written, GL untouched.
- `partial`: debits `min(balance, amount)`. Returns shortfall. If balance is 0, writes no transaction, returns `status='zero'`.
- `allow_negative`: debits the full amount even if it makes balance negative. **Restricted to credit module operations only.** Enforced in code by a checked list: if `source_module not in ALLOW_NEGATIVE_MODULES: raise`.

**GL posting:** A deduction is the reverse of a deposit — the savings liability is reduced:

```
Dr  savings liability account (account.liability_account_id)   amount
Cr  contra account (provided by caller)                        amount
```

`system_debit` accepts a `contra_account_id` argument. The caller (`FeeCollectionService`) passes `fee_type.gl_receivable_account_code` as the contra account. This keeps the savings module GL-agnostic about fee accounting — it only knows "debit the savings account against a contra."

The _collection_ journal entry is posted by `FeeCollectionService`, not by `system_debit`. `system_debit` creates the `savings_transactions` row and posts the savings-side GL entry. See §5.2.

### 3.4 `SavingsService.system_credit()` mirror

Same signature but reversed GL and adds `SYSTEM_CREDIT` transaction type. Used by loan disbursement to savings (credit module), refunds. v1 fees does not use `system_credit` but the method ships now since it's symmetric.

### 3.5 Authorization constraint

`system_debit` and `system_credit` are **not callable from API routes**. They are internal service methods.

CI enforcement: a ripgrep check in CI fails if `system_debit` or `system_credit` is called from:
- Any file matching `app/modules/*/api.py`
- `app/main.py`
- Any test that constructs a direct HTTP request to exercise these paths

Allowed callers in v1: `app/modules/fees/service.py` and `app/modules/fees/executors.py`.

---

## 4. GL Posting Logic

Two separate journal entries per fee with auto-collection:

### 4.1 Assessment entry (always posted, regardless of collection method)

```
Dr  fee receivable (fee_type.gl_receivable_account_code)   amount
Cr  fee income     (fee_type.gl_income_account_code)        amount
```

This follows accrual-basis revenue recognition: income is recognized when the fee is assessed (earned), not when collected.

### 4.2 Collection entry (posted when fee is paid)

**For `savings_deduction`:**
```
Dr  savings liability (savings_account.liability_account_id)    collected_amount
Cr  fee receivable    (fee_type.gl_receivable_account_code)     collected_amount
```

**For `cash`:**
```
Dr  cash account (provided by teller at collection time)   collected_amount
Cr  fee receivable (fee_type.gl_receivable_account_code)   collected_amount
```

**For `journal_voucher`:**
```
Dr  contra account (provided by staff)   collected_amount
Cr  fee receivable                       collected_amount
```

All entries posted via `LedgerService.post_journal_entry(...)`. Fees module never touches `journal_entries` or `journal_lines` directly.

---

## 5. Service Layer

### 5.1 `FeeAssessmentService`

**The only path to creating assessments.**

```python
async def assess(
    self,
    *,
    fee_type: FeeType,
    target_type: str,
    target_id: uuid.UUID,
    period_start: date,
    period_end: date | None,
    triggered_by_event_id: uuid.UUID | None,
    actor: uuid.UUID,
    idempotency_key: str,
) -> FeeAssessment
```

Behaviour:
1. Check `UNIQUE(fee_type_id, target_type, target_id, period_start)` — if exists, return existing assessment (idempotent).
2. Snapshot `fee_type.amount` and `fee_type.currency` onto the assessment row.
3. Post the assessment GL entry (Dr receivable, Cr income) via `LedgerService`.
4. Insert `FeeAssessment` row.
5. Flush (within the caller's transaction).
6. If `fee_type.requires_collection = true`, call `FeeCollectionService.auto_collect(assessment)` in the same transaction.
7. Return assessment.

### 5.2 `FeeCollectionService`

```python
async def collect(
    self,
    *,
    assessment_id: uuid.UUID,
    amount: Decimal,
    method: str,               # savings_deduction | cash | journal_voucher
    collected_by: uuid.UUID,
    idempotency_key: str,
    contra_account_id: uuid.UUID | None = None,  # required for cash/journal_voucher
    savings_account_id: uuid.UUID | None = None, # required for savings_deduction
) -> FeeCollection
```

**`auto_collect(assessment)` (internal, called by FeeAssessmentService):**
1. Determine the member's primary savings account (see §5.3).
2. Call `SavingsService.system_debit(savings_account_id, assessment.amount, reason='FEE_COLLECTION', source_module='fees', source_id=assessment.id, on_insufficient_funds='partial')`.
3. Receive `SystemDebitResult`.
4. Post the collection GL entry (Dr savings liability, Cr receivable) for `result.debited_amount`.
5. Insert `FeeCollection` row for `result.debited_amount`.
6. Update `assessment.status`:
   - `result.shortfall_amount == 0` → `paid`, set `paid_at`
   - `result.shortfall_amount > 0 and result.debited_amount > 0` → `partially_paid`
   - `result.status == 'zero'` → remain `assessed` (no collection row written, no GL entry)
7. Return `FeeCollection` (or None if zero-balance case).

### 5.3 Primary Savings Account Resolution

For `applicable_to='member'` fees, collection deducts from the member's **first active savings account** (ordered by `created_at ASC`). If the member has no savings account, leave assessment as `assessed` (becomes a pure receivable).

This is not a "primary account" concept in the data model — it's a selection rule in `FeeCollectionService`. When credit module ships, this rule may be refined (e.g., "loan repayment deducts from the account linked to the loan product"). Document the rule clearly.

---

## 6. Trigger Mechanisms

### 6.1 Event-triggered assessments

An outbox consumer subscribed to all event types that fee_types register.

On receiving event `event_type=X`:
1. Check `processed_events` table — if already processed, skip (at-least-once delivery contract).
2. Query `fee_types WHERE trigger_kind='event' AND event_name=X AND is_active=true`.
3. For each matching fee type, determine the target entity from the event payload.
4. Call `FeeAssessmentService.assess(...)` for each.
5. Mark event processed.

Initial consumer handles: `MemberActivated` → assesses `MEMBERSHIP` fee against the member.

### 6.2 Schedule-triggered assessments

Celery beat task `assess_scheduled_fees` runs **daily** per tenant.

Pattern: same `asyncio.run()` + fresh engine + iterate `platform.tenants` pattern as `cleanup_sessions` in `app/modules/iam/beat.py`.

Per tenant:
1. Query `fee_types WHERE trigger_kind='schedule' AND is_active=true`.
2. For each fee type, compute the population due based on `schedule_config` and last-assessment date.
   - `ANNUAL_SUB`: members with `status='active'` whose latest `fee_assessment` for this fee type has `period_end < today`, OR active members who have never been assessed.
3. Call `FeeAssessmentService.assess(...)` for each due member. Idempotent — double-runs safe.

### 6.3 Manual assessments

`POST /fees/assessments` endpoint (admin only) triggers `FeeAssessmentService.assess(...)` directly with `triggered_by_event_id=None`.

---

## 7. Partial Collection Retry

A Celery beat task `retry_partial_fee_collections` runs **daily** per tenant.

1. Iterate `fee_assessments WHERE status IN ('assessed', 'partially_paid')` and `due_at IS NULL OR due_at <= today`.
2. For each assessment with `requires_collection=true` on its fee type:
   - Determine savings account.
   - Attempt `FeeCollectionService.auto_collect(assessment)` (idempotent — checks existing collections).
3. Log summary: `N assessments retried, M fully collected, K still partially_paid`.

This prevents partial receivables becoming permanently abandoned.

---

## 8. Tenant Provisioning Seed

At tenant provisioning, seed two fee types (idempotent — `INSERT ... ON CONFLICT (code) DO NOTHING`):

**MEMBERSHIP fee:**
```json
{
  "code": "MEMBERSHIP",
  "name": "Membership Registration Fee",
  "applicable_to": "member",
  "amount_kind": "fixed",
  "amount": <from provisioning payload, e.g. 20000>,
  "currency": "UGX",
  "trigger_kind": "event",
  "event_name": "MemberActivated",
  "gl_income_account_code": "4001",
  "gl_receivable_account_code": "1101",
  "is_active": true,
  "requires_collection": true
}
```

**ANNUAL_SUB fee:**
```json
{
  "code": "ANNUAL_SUB",
  "name": "Annual Subscription Fee",
  "applicable_to": "member",
  "amount_kind": "fixed",
  "amount": <from provisioning payload, e.g. 50000>,
  "currency": "UGX",
  "trigger_kind": "schedule",
  "schedule_config": {"anchor": "tenant_financial_year_start", "recurrence": "yearly"},
  "gl_income_account_code": "4002",
  "gl_receivable_account_code": "1102",
  "is_active": true,
  "requires_collection": true
}
```

The `anchor: "tenant_financial_year_start"` references the tenant's configured financial year start month (a field to be added to the `platform.tenants` table, defaulting to January).

---

## 9. API Endpoints

All under `/fees/`. Require authenticated tenant user.

| Method | Path | Access | Notes |
|--------|------|--------|-------|
| `GET` | `/fees/types` | Any authenticated user | List active fee types. `?include_inactive=true` for admins |
| `GET` | `/fees/types/{id}` | Any authenticated user | Detail |
| `POST` | `/fees/types` | Admin + maker-checker | Create new fee type |
| `PATCH` | `/fees/types/{id}` | Admin + maker-checker | Update (deactivation, rate change). Old assessments retain snapshotted amounts |
| `GET` | `/fees/assessments` | Any authenticated user | List. Filters: `?status=`, `?member_id=`, `?fee_type_code=` |
| `GET` | `/fees/assessments/{id}` | Any authenticated user | Detail with collections list |
| `POST` | `/fees/assessments` | Admin (manual trigger) | Manually assess a fee |
| `POST` | `/fees/collections` | Teller or Admin | Manual collection capture |

**Not in v1:** waiver endpoint, reversal endpoint, assessment-edit endpoint.

---

## 10. Audit Trail

Every system-initiated debit/credit writes an `audit_log` entry:
- `actor_type='system'`
- `actor_id=NULL` (nil UUID as record_id)
- `source_module` and `source_id` populated
- `narration` captures fee type name and period

End-of-day reporting query (columns designed to support this; reporting module builds the UI):
```sql
SELECT reason, count(*), sum(amount)
FROM savings_transactions
WHERE created_at::date = current_date
  AND source_module IS NOT NULL
GROUP BY reason;
```

---

## 11. Deferred to Fees v2

The following are intentionally out of scope for v1. Columns/enum values may exist; runtime support does not.

- `percentage` and `tiered` amount_kind execution paths
- Multi-currency fee handling when `fee.currency != target.currency`
- Fee waiver workflow (columns `waived_by`, `waiver_reason` exist; API and maker-checker flow deferred)
- Pro-rated fees on partial periods (member joins mid-year)
- Member/group-level fee discounts or overrides
- Fee statement generation
- Fee reversal (distinct from waiver — reversal = "we should not have charged this at all")
- Fee notification triggers (SMS/email on assessment, on overdue)
- Dormancy fees, NSF fees, loan-related fees (new `fee_type` rows when those modules ship)
- `allow_negative` for `system_debit` (column exists, checked allowlist enforces v1 scope)

---

## 12. CLAUDE.md Additions

Add to the `## Architectural rules` and `## Core module contracts` sections:

```
- Fees module never writes to journal tables directly. Always via LedgerService.
- Fees module never mutates savings balances directly. Always via SavingsService.system_debit/system_credit.
- Assessment is idempotent via (fee_type_id, target_type, target_id, period_start). Never bypass the unique constraint.
- Assessment amount is snapshotted onto fee_assessments at creation. Changing fee_type.amount does not retroactively change assessed rows.
- system_debit and system_credit are not callable from HTTP routes. CI enforces this.
- Every savings_transactions row that is system-initiated MUST have source_module and source_id populated.
- Partial collection is a first-class outcome, not an error. Callers must handle shortfall_amount > 0 explicitly.
- System-initiated transactions on savings accounts go through system_debit/system_credit. Maker-checker is on the originating operation, not the financial movement itself.
```

---

## 13. CI Check

Add to CI pipeline: ripgrep step fails if `system_debit` or `system_credit` is called from:
- Any `app/modules/*/api.py`
- `app/main.py`

Allowed callers in v1: `app/modules/fees/service.py`, `app/modules/fees/executors.py`.

---

## 14. Implementation Order

Each step is a discrete unit of work (maps to one implementation session):

1. **Migrations** — `fee_types`, `fee_assessments`, `fee_collections` tables + indexes + unique constraints. Also: extend `savings_transactions` with `transaction_type` enum values, `source_module`, `source_id`, `reason` columns.
2. **SQLAlchemy models + Pydantic schemas** — `FeeType`, `FeeAssessment`, `FeeCollection`. `SystemDebitResult` dataclass.
3. **`SavingsService.system_debit()` and `system_credit()`** — with `on_insufficient_funds` parameter, full test suite.
4. **`FeeAssessmentService`** — `assess()` method, idempotency via unique constraint, assessment GL entry, auto-collect hook.
5. **`FeeCollectionService`** — `collect()`, `auto_collect()`, partial collection logic, collection GL entry, assessment status update.
6. **Outbox consumer** — event-triggered assessments, `MemberActivated` → `MEMBERSHIP` fee.
7. **Celery beat tasks** — `assess_scheduled_fees` (daily, per-tenant) and `retry_partial_fee_collections` (daily, per-tenant). Register in `celery_app.py`.
8. **Tenant provisioning seed** — `MEMBERSHIP` and `ANNUAL_SUB` fee types seeded on tenant creation. Add `financial_year_start_month` to `platform.tenants`.
9. **API endpoints** — fee_types CRUD (maker-checker on write), assessments read + manual, collections create.
10. **Tests** — unit + integration across all of the above.
11. **CLAUDE.md updates** — boundary rules from §12.
