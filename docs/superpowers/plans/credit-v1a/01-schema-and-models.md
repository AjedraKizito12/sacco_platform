# Sub-plan 01 — Schema and Models

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> or `superpowers:executing-plans`. Complete all tasks in order. Run verification criteria
> at the end before marking this sub-plan done.

**Goal:** Lay the complete database schema and SQLAlchemy model layer for the credit module.
No service logic. No API. No tests beyond import/smoke checks and two targeted unit tests
for the schema additions to existing tables.

**Architecture:** Migration 010 extends `journal_lines` with sub-ledger tagging columns,
extends `savings_transactions` with two new transaction types, and creates five new credit
tables plus one sequence. Models mirror the migration exactly. Two existing service files
(`ledger/models.py`, `ledger/service.py`) gain backward-compatible additions.

**Tech Stack:** SQLAlchemy 2.0 async mapped columns, Alembic `op.*`, pytest-asyncio,
`sqlalchemy.dialects.postgresql.ARRAY`

---

## Required Reading

Before starting, read these files in full:

- `docs/superpowers/specs/2026-05-27-credit-v1a-design.md` §3, §13
- `alembic/tenant/versions/009_fees_tables.py` — migration style
- `app/modules/ledger/models.py` — current `JournalLine` definition (lines 109–151)
- `app/modules/savings/models.py` — current `SavingsTransaction` definition
- `app/modules/fees/models.py` — model style to follow
- `tests/conftest.py` — import + sequence pattern
- `tests/modules/ledger/test_service.py` lines 1–60 — test helper style

---

## File Map

```
New
  alembic/tenant/versions/010_credit_tables.py
  app/modules/credit/__init__.py
  app/modules/credit/models.py
  app/modules/credit/services/__init__.py
  tests/modules/credit/__init__.py
  tests/modules/credit/test_schema.py        ← two targeted tests, no service logic

Modified
  app/modules/ledger/models.py               add sub_ledger_type, sub_ledger_id to JournalLine
  app/modules/ledger/service.py              post_journal_entry passes sub_ledger fields from line dicts
  app/modules/savings/models.py              extend ck_savtx_transaction_type CHECK
  tests/conftest.py                          import credit models; create loan_number_seq
```

---

## Task 1 — Migration 010

**Files:**
- Create: `alembic/tenant/versions/010_credit_tables.py`

- [ ] **Step 1: Write the migration file**

```python
# alembic/tenant/versions/010_credit_tables.py
"""Credit module: sub-ledger columns on journal_lines; EXTERNAL_CREDIT/EXTERNAL_DEBIT
on savings_transactions; loan_products, loan_applications, loans, loan_installments,
loan_repayments tables; loan_number_seq sequence.

Revision: 010
Depends on: 009
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── journal_lines: add sub-ledger tagging columns ─────────────────────────
    op.add_column("journal_lines", sa.Column("sub_ledger_type", sa.Text(), nullable=True))
    op.add_column("journal_lines", sa.Column("sub_ledger_id", sa.UUID(), nullable=True))
    op.create_index(
        "ix_jl_sub_ledger",
        "journal_lines",
        ["sub_ledger_type", "sub_ledger_id"],
        postgresql_where=sa.text("sub_ledger_id IS NOT NULL"),
    )

    # ── savings_transactions: extend transaction_type CHECK ───────────────────
    op.drop_constraint("ck_savtx_transaction_type", "savings_transactions")
    op.create_check_constraint(
        "ck_savtx_transaction_type",
        "savings_transactions",
        "transaction_type IN ('deposit', 'withdrawal', 'SYSTEM_DEBIT', 'SYSTEM_CREDIT',"
        " 'EXTERNAL_CREDIT', 'EXTERNAL_DEBIT')",
    )

    # ── loan_products ─────────────────────────────────────────────────────────
    op.create_table(
        "loan_products",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("interest_method", sa.Text(), nullable=False),
        sa.Column("annual_interest_rate", sa.Numeric(19, 4), nullable=False),
        sa.Column("repayment_frequency", sa.Text(), nullable=False),
        sa.Column("max_term_periods", sa.Integer(), nullable=False),
        sa.Column("min_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("max_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("required_approvals", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("disbursement_destinations", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("repayment_allocation", sa.Text(), nullable=False, server_default="INTEREST_PRINCIPAL"),
        sa.Column("gl_principal_receivable_code", sa.Text(), nullable=False),
        sa.Column("gl_interest_receivable_code", sa.Text(), nullable=False),
        sa.Column("gl_interest_income_code", sa.Text(), nullable=False),
        sa.Column("gl_loan_loss_expense_code", sa.Text(), nullable=True),
        sa.Column("penalty_fee_type_code", sa.Text(), nullable=True),
        sa.Column("write_off_threshold", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "interest_method IN ('flat', 'reducing_balance')",
            name="ck_lp_interest_method",
        ),
        sa.CheckConstraint(
            "repayment_frequency IN ('weekly', 'biweekly', 'monthly', 'quarterly')",
            name="ck_lp_repayment_frequency",
        ),
        sa.CheckConstraint("annual_interest_rate >= 0", name="ck_lp_annual_rate"),
        sa.CheckConstraint("min_amount > 0", name="ck_lp_min_amount"),
        sa.CheckConstraint("max_amount >= min_amount", name="ck_lp_max_gte_min"),
        sa.CheckConstraint("max_term_periods > 0", name="ck_lp_max_term"),
        sa.CheckConstraint("required_approvals >= 1", name="ck_lp_required_approvals"),
        sa.CheckConstraint("write_off_threshold >= 0", name="ck_lp_write_off_threshold"),
        sa.CheckConstraint(
            "repayment_allocation IN ('INTEREST_PRINCIPAL')",
            name="ck_lp_repayment_allocation",
        ),
    )
    op.create_index("ix_lp_is_active", "loan_products", ["is_active"])

    # ── loan_applications ─────────────────────────────────────────────────────
    op.create_table(
        "loan_applications",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("loan_product_id", sa.UUID(), sa.ForeignKey("loan_products.id", name="fk_la_product"), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("requested_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("requested_term_periods", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("disbursement_destination", sa.Text(), nullable=False),
        sa.Column("disbursement_account_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="submitted"),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("approved_amount", sa.Numeric(19, 4), nullable=True),
        sa.Column("approved_term_periods", sa.Integer(), nullable=True),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_la_idempotency_key"),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'under_review', 'approved', 'rejected', 'withdrawn', 'cancelled')",
            name="ck_la_status",
        ),
        sa.CheckConstraint(
            "disbursement_destination IN ('member_savings', 'cash', 'internal_gl')",
            name="ck_la_disbursement_destination",
        ),
        sa.CheckConstraint("requested_amount > 0", name="ck_la_requested_amount"),
        sa.CheckConstraint("requested_term_periods > 0", name="ck_la_requested_term"),
    )
    op.create_index("ix_la_member_id", "loan_applications", ["member_id"])
    op.create_index("ix_la_status", "loan_applications", ["status"])
    op.create_index("ix_la_loan_product_id", "loan_applications", ["loan_product_id"])

    # ── loans ─────────────────────────────────────────────────────────────────
    op.create_table(
        "loans",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("loan_reference", sa.Text(), nullable=False),
        sa.Column("loan_application_id", sa.UUID(), sa.ForeignKey("loan_applications.id", name="fk_ln_application"), nullable=False),
        sa.Column("loan_product_id", sa.UUID(), sa.ForeignKey("loan_products.id", name="fk_ln_product"), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        # Snapshotted product terms
        sa.Column("principal_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("interest_method", sa.Text(), nullable=False),
        sa.Column("annual_interest_rate", sa.Numeric(19, 4), nullable=False),
        sa.Column("repayment_frequency", sa.Text(), nullable=False),
        sa.Column("term_periods", sa.Integer(), nullable=False),
        sa.Column("repayment_allocation", sa.Text(), nullable=False),
        sa.Column("disbursement_destination", sa.Text(), nullable=False),
        sa.Column("disbursement_account_id", sa.UUID(), nullable=True),
        # Snapshotted GL account IDs (resolved from codes at disbursement)
        sa.Column("gl_principal_receivable_id", sa.UUID(), nullable=False),
        sa.Column("gl_interest_receivable_id", sa.UUID(), nullable=False),
        sa.Column("gl_interest_income_id", sa.UUID(), nullable=False),
        sa.Column("gl_disbursement_account_id", sa.UUID(), nullable=False),
        sa.Column("gl_loan_loss_expense_id", sa.UUID(), nullable=True),
        # Balance snapshot (single-writer: app/modules/credit/services/ only)
        sa.Column("outstanding_principal", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("accrued_interest", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("accrued_penalties", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("total_paid_principal", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("total_paid_interest", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("total_paid_penalties", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("total_written_off", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("last_repayment_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_repayment_amount", sa.Numeric(19, 4), nullable=True),
        # Dates
        sa.Column("disbursed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("first_repayment_due", sa.Date(), nullable=True),
        sa.Column("maturity_date", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("disbursed_by", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("loan_reference", name="uq_ln_loan_reference"),
        sa.UniqueConstraint("loan_application_id", name="uq_ln_application_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_ln_idempotency_key"),
        sa.CheckConstraint(
            "status IN ('disbursing', 'disbursed', 'in_arrears', 'closed', 'written_off')",
            name="ck_ln_status",
        ),
        sa.CheckConstraint("outstanding_principal >= 0", name="ck_ln_outstanding_principal"),
        sa.CheckConstraint("accrued_interest >= 0", name="ck_ln_accrued_interest"),
        sa.CheckConstraint("accrued_penalties >= 0", name="ck_ln_accrued_penalties"),
        sa.CheckConstraint("principal_amount > 0", name="ck_ln_principal_amount"),
    )
    op.create_index("ix_ln_member_id", "loans", ["member_id"])
    op.create_index("ix_ln_status", "loans", ["status"])
    op.create_index("ix_ln_loan_product_id", "loans", ["loan_product_id"])

    # ── loan_installments ─────────────────────────────────────────────────────
    op.create_table(
        "loan_installments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("loan_id", sa.UUID(), sa.ForeignKey("loans.id", name="fk_li_loan"), nullable=False),
        sa.Column("period_number", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("principal_due", sa.Numeric(19, 4), nullable=False),
        sa.Column("interest_due", sa.Numeric(19, 4), nullable=False),
        sa.Column("total_due", sa.Numeric(19, 4), nullable=False),
        sa.Column("principal_paid", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("interest_paid", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("paid_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("loan_id", "period_number", name="uq_li_loan_period"),
        sa.CheckConstraint(
            "status IN ('pending', 'partial', 'paid', 'overdue')",
            name="ck_li_status",
        ),
        sa.CheckConstraint("principal_due >= 0", name="ck_li_principal_due"),
        sa.CheckConstraint("interest_due >= 0", name="ck_li_interest_due"),
        sa.CheckConstraint("period_number >= 1", name="ck_li_period_number"),
    )
    op.create_index("ix_li_loan_id", "loan_installments", ["loan_id"])
    op.create_index("ix_li_due_date_status", "loan_installments", ["due_date", "status"])

    # ── loan_repayments ───────────────────────────────────────────────────────
    op.create_table(
        "loan_repayments",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("loan_id", sa.UUID(), sa.ForeignKey("loans.id", name="fk_lr_loan"), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("principal_applied", sa.Numeric(19, 4), nullable=False),
        sa.Column("interest_applied", sa.Numeric(19, 4), nullable=False),
        sa.Column("penalties_applied", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("overpayment", sa.Numeric(19, 4), nullable=False, server_default="0"),
        sa.Column("payment_account_id", sa.UUID(), nullable=False),
        sa.Column("journal_entry_id", sa.UUID(), sa.ForeignKey("journal_entries.id", name="fk_lr_journal"), nullable=False),
        sa.Column("posted_by", sa.UUID(), nullable=False),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_lr_idempotency_key"),
        sa.CheckConstraint("amount > 0", name="ck_lr_amount"),
        sa.CheckConstraint("principal_applied >= 0", name="ck_lr_principal_applied"),
        sa.CheckConstraint("interest_applied >= 0", name="ck_lr_interest_applied"),
        sa.CheckConstraint("penalties_applied >= 0", name="ck_lr_penalties_applied"),
        sa.CheckConstraint("overpayment >= 0", name="ck_lr_overpayment"),
    )
    op.create_index("ix_lr_loan_id", "loan_repayments", ["loan_id"])

    # ── loan_number_seq ───────────────────────────────────────────────────────
    op.execute("CREATE SEQUENCE loan_number_seq START 1")


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS loan_number_seq")
    op.drop_table("loan_repayments")
    op.drop_table("loan_installments")
    op.drop_table("loans")
    op.drop_table("loan_applications")
    op.drop_table("loan_products")
    op.drop_constraint("ck_savtx_transaction_type", "savings_transactions")
    op.create_check_constraint(
        "ck_savtx_transaction_type",
        "savings_transactions",
        "transaction_type IN ('deposit', 'withdrawal', 'SYSTEM_DEBIT', 'SYSTEM_CREDIT')",
    )
    op.drop_index("ix_jl_sub_ledger", "journal_lines")
    op.drop_column("journal_lines", "sub_ledger_id")
    op.drop_column("journal_lines", "sub_ledger_type")
```

- [ ] **Step 2: Run the migration**

```bash
docker compose exec api alembic -c alembic/tenant/env.py upgrade head
```

Expected: no errors, migration `010` applied.

- [ ] **Step 3: Verify the new tables exist**

```bash
docker compose exec db psql -U sacco sacco -c "\dt tenant_test.*" 2>/dev/null | grep -E "loan|installment|repayment"
```

Expected output includes: `loan_products`, `loan_applications`, `loans`, `loan_installments`, `loan_repayments`.

- [ ] **Step 4: Verify the sequence exists**

```bash
docker compose exec db psql -U sacco sacco -c "SELECT nextval('tenant_test.loan_number_seq');"
```

Expected: `1`

- [ ] **Step 5: Commit**

```bash
git add alembic/tenant/versions/010_credit_tables.py
git commit -m "feat(credit): migration 010 — credit tables + journal_lines sub_ledger + savings EXTERNAL types"
```

---

## Task 2 — JournalLine Model + LedgerService Sub-Ledger Support

**Files:**
- Modify: `app/modules/ledger/models.py`
- Modify: `app/modules/ledger/service.py`
- Modify: `tests/modules/ledger/test_service.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/modules/ledger/test_service.py`:

```python
async def test_post_journal_entry_stores_sub_ledger_fields(test_engine):
    """sub_ledger_type and sub_ledger_id on a line dict are stored on JournalLine."""
    import uuid as _uuid
    from sqlalchemy import select as sa_select

    session = await _new_session(test_engine)
    try:
        svc = LedgerService(session)
        actor = _uuid.uuid4()
        asset = await svc.create_account(code="1-SL", name="Asset SL", account_type="asset", created_by=actor)
        liability = await svc.create_account(code="2-SL", name="Liab SL", account_type="liability", created_by=actor)

        fake_loan_id = _uuid.uuid4()
        entry = await svc.post_journal_entry(
            reference="SL-TEST",
            description="Sub-ledger test",
            posted_by=actor,
            idempotency_key=f"sl-test-{fake_loan_id}",
            lines=[
                {
                    "account_id": asset.id,
                    "debit_amount": Decimal("100"),
                    "credit_amount": Decimal("0"),
                    "sub_ledger_type": "loan",
                    "sub_ledger_id": fake_loan_id,
                },
                {
                    "account_id": liability.id,
                    "debit_amount": Decimal("0"),
                    "credit_amount": Decimal("100"),
                    "sub_ledger_type": "loan",
                    "sub_ledger_id": fake_loan_id,
                },
            ],
        )
        await session.commit()

        # Re-fetch lines and verify sub_ledger fields persisted.
        lines = list(
            (await session.execute(
                sa_select(JournalLine).where(JournalLine.journal_entry_id == entry.id)
            )).scalars().all()
        )
        assert len(lines) == 2
        for line in lines:
            assert line.sub_ledger_type == "loan"
            assert line.sub_ledger_id == fake_loan_id
    finally:
        await session.close()
        await _cleanup(test_engine)
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
pytest tests/modules/ledger/test_service.py::test_post_journal_entry_stores_sub_ledger_fields -v
```

Expected: `FAILED` — `AttributeError: type object 'JournalLine' has no attribute 'sub_ledger_type'`

- [ ] **Step 3: Update `app/modules/ledger/models.py`**

Add two mapped columns to `JournalLine` after the existing `description` column (line 135),
and add the index to `__table_args__`:

```python
# In class JournalLine, after description:
sub_ledger_type: Mapped[str | None] = mapped_column(Text, nullable=True)
sub_ledger_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True), nullable=True
)
```

Update `__table_args__` in `JournalLine` — replace the existing tuple with:

```python
__table_args__ = (
    CheckConstraint(
        "debit_amount >= 0 AND credit_amount >= 0"
        " AND (debit_amount > 0 OR credit_amount > 0)"
        " AND NOT (debit_amount > 0 AND credit_amount > 0)",
        name="ck_jl_amounts",
    ),
    Index("ix_jl_journal_entry_id", "journal_entry_id"),
    Index("ix_jl_account_id", "account_id"),
    Index(
        "ix_jl_sub_ledger",
        "sub_ledger_type",
        "sub_ledger_id",
        postgresql_where=text("sub_ledger_id IS NOT NULL"),
    ),
)
```

Add the missing import `text` to `app/modules/ledger/models.py` (it's already imported as
`func` from `sqlalchemy`; add `text` to the same import line):

```python
from sqlalchemy import (
    UUID,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    Text,
    TIMESTAMP,
    UniqueConstraint,
    func,
    text,
)
```

- [ ] **Step 4: Update `app/modules/ledger/service.py` — `post_journal_entry`**

In the `for ln in lines:` loop inside `post_journal_entry` (around line 122),
replace the existing `session.add(JournalLine(...))` call with:

```python
for ln in lines:
    sub_ledger_id_val = ln.get("sub_ledger_id")
    self._session.add(
        JournalLine(
            journal_entry_id=entry.id,
            account_id=uuid.UUID(str(ln["account_id"])),
            debit_amount=Decimal(str(ln["debit_amount"])),
            credit_amount=Decimal(str(ln["credit_amount"])),
            description=ln.get("description"),
            sub_ledger_type=ln.get("sub_ledger_type"),
            sub_ledger_id=uuid.UUID(str(sub_ledger_id_val)) if sub_ledger_id_val is not None else None,
        )
    )
```

- [ ] **Step 5: Run the test to confirm it passes**

```bash
pytest tests/modules/ledger/test_service.py::test_post_journal_entry_stores_sub_ledger_fields -v
```

Expected: `PASSED`

- [ ] **Step 6: Run existing ledger tests to confirm no regressions**

```bash
pytest tests/modules/ledger/ -v
```

Expected: all existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add app/modules/ledger/models.py app/modules/ledger/service.py tests/modules/ledger/test_service.py
git commit -m "feat(ledger): add sub_ledger_type/sub_ledger_id to JournalLine; pass through in post_journal_entry"
```

---

## Task 3 — SavingsTransaction CHECK Constraint Update

**Files:**
- Modify: `app/modules/savings/models.py`
- Modify: `tests/modules/savings/test_service.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/modules/savings/test_service.py`. The test directly inserts a
`SavingsTransaction` row with `transaction_type='EXTERNAL_CREDIT'` to verify the model
accepts it. (The service methods `record_external_credit`/`record_external_debit` are
implemented in sub-plan 04; this test validates the schema only.)

First add the necessary imports at the top of the test file (they may already be there):
```python
from app.modules.ledger.models import JournalEntry
```

Then append the test:

```python
async def test_savings_transaction_accepts_external_credit_type(test_engine):
    """EXTERNAL_CREDIT is a valid transaction_type — CHECK constraint allows it."""
    import uuid as _uuid
    from sqlalchemy import insert
    from sqlalchemy.ext.asyncio import async_sessionmaker

    factory = async_sessionmaker(test_engine, expire_on_commit=False)

    # Set up: GL account + savings product + savings account + a journal entry to reference.
    session = await _new_session(test_engine)
    try:
        actor = _uuid.uuid4()
        ledger_svc = LedgerService(session)
        cash = await ledger_svc.create_account(
            code=f"1-EXT-{_uuid.uuid4().hex[:4]}", name="Cash EXT",
            account_type="asset", created_by=actor,
        )
        liab = await ledger_svc.create_account(
            code=f"2-EXT-{_uuid.uuid4().hex[:4]}", name="Savings EXT",
            account_type="liability", created_by=actor,
        )
        # Post a dummy journal entry (represents the external module's GL entry).
        entry = await ledger_svc.post_journal_entry(
            reference="EXT-CR-TEST",
            description="Dummy external entry",
            posted_by=actor,
            idempotency_key=f"ext-cr-test-{_uuid.uuid4()}",
            lines=[
                {"account_id": cash.id, "debit_amount": Decimal("500"), "credit_amount": Decimal("0")},
                {"account_id": liab.id, "debit_amount": Decimal("0"), "credit_amount": Decimal("500")},
            ],
        )

        savings_svc = SavingsService(session)
        product = SavingsProduct(
            name="EXT Test Product",
            interest_rate=Decimal("5"),
            minimum_balance=Decimal("0"),
            liability_account_id=liab.id,
        )
        session.add(product)
        await session.flush()

        member_svc = MemberService(session)
        from datetime import date as _date
        member = await member_svc.register_member(
            full_name="EXT Test Member",
            date_of_birth=_date(1990, 1, 1),
            gender="female",
            created_by=actor,
        )
        account = await savings_svc.open_account(member_id=member.id, savings_product_id=product.id)

        # Insert EXTERNAL_CREDIT row directly (bypassing service — testing model/schema only).
        txn = SavingsTransaction(
            savings_account_id=account.id,
            transaction_type="EXTERNAL_CREDIT",
            amount=Decimal("500"),
            journal_entry_id=entry.id,
            posted_by=actor,
            idempotency_key=f"ext-cr-direct-{_uuid.uuid4()}",
            source_module="credit",
            source_id=_uuid.uuid4(),
            reason="LOAN_DISBURSEMENT",
        )
        session.add(txn)
        await session.flush()
        await session.commit()

        assert txn.id is not None
        assert txn.transaction_type == "EXTERNAL_CREDIT"
    finally:
        await session.close()
        # cleanup handled by next test or session teardown
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
pytest tests/modules/savings/test_service.py::test_savings_transaction_accepts_external_credit_type -v
```

Expected: `FAILED` — either a DB CHECK violation or `AttributeError`.

> **Note:** If you see a CHECK violation from Postgres, that confirms the migration has
> not yet been reflected in the model. If you see `AttributeError`, the model still has
> the old constraint string.

- [ ] **Step 3: Update `app/modules/savings/models.py`**

In `SavingsTransaction.__table_args__`, replace the existing `ck_savtx_transaction_type`
`CheckConstraint` with:

```python
CheckConstraint(
    "transaction_type IN ('deposit', 'withdrawal', 'SYSTEM_DEBIT', 'SYSTEM_CREDIT',"
    " 'EXTERNAL_CREDIT', 'EXTERNAL_DEBIT')",
    name="ck_savtx_transaction_type",
),
```

The migration already dropped and recreated this constraint on the DB side (Task 1).
This step keeps the Python model definition in sync.

- [ ] **Step 4: Run the test to confirm it passes**

```bash
pytest tests/modules/savings/test_service.py::test_savings_transaction_accepts_external_credit_type -v
```

Expected: `PASSED`

- [ ] **Step 5: Run full savings test suite for regressions**

```bash
pytest tests/modules/savings/ -v
```

Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/modules/savings/models.py tests/modules/savings/test_service.py
git commit -m "feat(savings): extend transaction_type CHECK to include EXTERNAL_CREDIT, EXTERNAL_DEBIT"
```

---

## Task 4 — Credit Module Models

**Files:**
- Create: `app/modules/credit/__init__.py`
- Create: `app/modules/credit/models.py`
- Create: `app/modules/credit/services/__init__.py`
- Create: `tests/modules/credit/__init__.py`

- [ ] **Step 1: Create `app/modules/credit/__init__.py`**

```python
```
(Empty file.)

- [ ] **Step 2: Create `app/modules/credit/services/__init__.py`**

```python
```
(Empty file.)

- [ ] **Step 3: Create `tests/modules/credit/__init__.py`**

```python
```
(Empty file.)

- [ ] **Step 4: Create `app/modules/credit/models.py`**

```python
# app/modules/credit/models.py
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class LoanProduct(AuditableMixin, Base):
    """Loan product configuration. Terms are snapshotted onto loans at disbursement.

    No schema= — resolved at runtime via SET LOCAL search_path.
    """

    __tablename__ = "loan_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    interest_method: Mapped[str] = mapped_column(Text, nullable=False)
    annual_interest_rate: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    repayment_frequency: Mapped[str] = mapped_column(Text, nullable=False)
    max_term_periods: Mapped[int] = mapped_column(Integer, nullable=False)
    min_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    max_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    required_approvals: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    disbursement_destinations: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    repayment_allocation: Mapped[str] = mapped_column(Text, nullable=False, default="INTEREST_PRINCIPAL")
    gl_principal_receivable_code: Mapped[str] = mapped_column(Text, nullable=False)
    gl_interest_receivable_code: Mapped[str] = mapped_column(Text, nullable=False)
    gl_interest_income_code: Mapped[str] = mapped_column(Text, nullable=False)
    gl_loan_loss_expense_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    penalty_fee_type_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    write_off_threshold: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("interest_method IN ('flat', 'reducing_balance')", name="ck_lp_interest_method"),
        CheckConstraint(
            "repayment_frequency IN ('weekly', 'biweekly', 'monthly', 'quarterly')",
            name="ck_lp_repayment_frequency",
        ),
        CheckConstraint("annual_interest_rate >= 0", name="ck_lp_annual_rate"),
        CheckConstraint("min_amount > 0", name="ck_lp_min_amount"),
        CheckConstraint("max_amount >= min_amount", name="ck_lp_max_gte_min"),
        CheckConstraint("max_term_periods > 0", name="ck_lp_max_term"),
        CheckConstraint("required_approvals >= 1", name="ck_lp_required_approvals"),
        CheckConstraint("write_off_threshold >= 0", name="ck_lp_write_off_threshold"),
        CheckConstraint("repayment_allocation IN ('INTEREST_PRINCIPAL')", name="ck_lp_repayment_allocation"),
        Index("ix_lp_is_active", "is_active"),
    )


class LoanApplication(AuditableMixin, Base):
    """Loan application. Moves through lifecycle via ApprovalService.

    status progression: submitted → under_review → approved | rejected | withdrawn
    approved_amount / approved_term_periods may differ from requested values.
    """

    __tablename__ = "loan_applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loan_products.id", name="fk_la_product"), nullable=False
    )
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    requested_term_periods: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    disbursement_destination: Mapped[str] = mapped_column(Text, nullable=False)
    disbursement_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="submitted")
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    approved_term_periods: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_la_idempotency_key"),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'under_review', 'approved', 'rejected', 'withdrawn', 'cancelled')",
            name="ck_la_status",
        ),
        CheckConstraint(
            "disbursement_destination IN ('member_savings', 'cash', 'internal_gl')",
            name="ck_la_disbursement_destination",
        ),
        CheckConstraint("requested_amount > 0", name="ck_la_requested_amount"),
        CheckConstraint("requested_term_periods > 0", name="ck_la_requested_term"),
        Index("ix_la_member_id", "member_id"),
        Index("ix_la_status", "status"),
        Index("ix_la_loan_product_id", "loan_product_id"),
    )


class Loan(AuditableMixin, Base):
    """Active loan. Created at disbursement. Product terms snapshotted at creation.

    Balance snapshot columns (outstanding_principal, accrued_interest, accrued_penalties,
    total_paid_*, total_written_off) are the authoritative source for operational balance
    queries. GL is authoritative for accounting reports.

    SINGLE-WRITER: all snapshot mutations happen inside app/modules/credit/services/
    in the same DB transaction as the GL post. See CLAUDE.md credit module contracts.
    """

    __tablename__ = "loans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_reference: Mapped[str] = mapped_column(Text, nullable=False)
    loan_application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loan_applications.id", name="fk_ln_application"), nullable=False
    )
    loan_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loan_products.id", name="fk_ln_product"), nullable=False
    )
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # ── Snapshotted product terms ──────────────────────────────────────────────
    principal_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    interest_method: Mapped[str] = mapped_column(Text, nullable=False)
    annual_interest_rate: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    repayment_frequency: Mapped[str] = mapped_column(Text, nullable=False)
    term_periods: Mapped[int] = mapped_column(Integer, nullable=False)
    repayment_allocation: Mapped[str] = mapped_column(Text, nullable=False)
    disbursement_destination: Mapped[str] = mapped_column(Text, nullable=False)
    disbursement_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # ── Snapshotted GL account IDs ─────────────────────────────────────────────
    # FK omitted intentionally — consistent with savings.liability_account_id pattern.
    gl_principal_receivable_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    gl_interest_receivable_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    gl_interest_income_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    gl_disbursement_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    gl_loan_loss_expense_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # ── Balance snapshot ───────────────────────────────────────────────────────
    outstanding_principal: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    accrued_interest: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    accrued_penalties: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    total_paid_principal: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    total_paid_interest: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    total_paid_penalties: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    total_written_off: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    last_repayment_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_repayment_amount: Mapped[Decimal | None] = mapped_column(Numeric(19, 4), nullable=True)
    # ── Dates ─────────────────────────────────────────────────────────────────
    disbursed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    first_repayment_due: Mapped[date | None] = mapped_column(Date, nullable=True)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    disbursed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("loan_reference", name="uq_ln_loan_reference"),
        UniqueConstraint("loan_application_id", name="uq_ln_application_id"),
        UniqueConstraint("idempotency_key", name="uq_ln_idempotency_key"),
        CheckConstraint(
            "status IN ('disbursing', 'disbursed', 'in_arrears', 'closed', 'written_off')",
            name="ck_ln_status",
        ),
        CheckConstraint("outstanding_principal >= 0", name="ck_ln_outstanding_principal"),
        CheckConstraint("accrued_interest >= 0", name="ck_ln_accrued_interest"),
        CheckConstraint("accrued_penalties >= 0", name="ck_ln_accrued_penalties"),
        CheckConstraint("principal_amount > 0", name="ck_ln_principal_amount"),
        Index("ix_ln_member_id", "member_id"),
        Index("ix_ln_status", "status"),
        Index("ix_ln_loan_product_id", "loan_product_id"),
    )


class LoanInstallment(Base):
    """One row per scheduled repayment period. Append-only at disbursement;
    principal_paid / interest_paid / status / paid_at are updated by repayment service.

    No AuditableMixin — financial append-only table (CLAUDE.md rule 4).
    """

    __tablename__ = "loan_installments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loans.id", name="fk_li_loan"), nullable=False
    )
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    principal_due: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    interest_due: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    total_due: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    principal_paid: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    interest_paid: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    paid_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("loan_id", "period_number", name="uq_li_loan_period"),
        CheckConstraint("status IN ('pending', 'partial', 'paid', 'overdue')", name="ck_li_status"),
        CheckConstraint("principal_due >= 0", name="ck_li_principal_due"),
        CheckConstraint("interest_due >= 0", name="ck_li_interest_due"),
        CheckConstraint("period_number >= 1", name="ck_li_period_number"),
        Index("ix_li_loan_id", "loan_id"),
        Index("ix_li_due_date_status", "due_date", "status"),
    )


class LoanRepayment(Base):
    """One row per repayment capture. Append-only.

    principal_applied + interest_applied + penalties_applied + overpayment == amount.
    journal_entry_id references the GL entry posted in the same transaction.
    No AuditableMixin — append-only financial table (CLAUDE.md rule 4).
    """

    __tablename__ = "loan_repayments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loans.id", name="fk_lr_loan"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    principal_applied: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    interest_applied: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    penalties_applied: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    overpayment: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False, default=Decimal("0"))
    payment_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    journal_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entries.id", name="fk_lr_journal"), nullable=False
    )
    posted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    narration: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_lr_idempotency_key"),
        CheckConstraint("amount > 0", name="ck_lr_amount"),
        CheckConstraint("principal_applied >= 0", name="ck_lr_principal_applied"),
        CheckConstraint("interest_applied >= 0", name="ck_lr_interest_applied"),
        CheckConstraint("penalties_applied >= 0", name="ck_lr_penalties_applied"),
        CheckConstraint("overpayment >= 0", name="ck_lr_overpayment"),
        Index("ix_lr_loan_id", "loan_id"),
    )
```

- [ ] **Step 5: Verify the models import without errors**

```bash
python -c "from app.modules.credit.models import LoanProduct, LoanApplication, Loan, LoanInstallment, LoanRepayment; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add app/modules/credit/__init__.py app/modules/credit/models.py \
        app/modules/credit/services/__init__.py tests/modules/credit/__init__.py
git commit -m "feat(credit): SQLAlchemy models — LoanProduct, LoanApplication, Loan, LoanInstallment, LoanRepayment"
```

---

## Task 5 — Update conftest.py + Smoke Test

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Update `tests/conftest.py`**

In the `test_engine` fixture, after the existing model imports, add:

```python
import app.modules.credit.models  # noqa: F401 — registers credit tables in Base.metadata
```

After the line that creates `member_number_seq`, add:

```python
await conn.execute(
    text(f"CREATE SEQUENCE IF NOT EXISTS {TEST_TENANT_SCHEMA}.loan_number_seq START 1")
)
```

The updated block in full (replace the existing sequence section):

```python
# Create tenant sequences that are not part of SQLAlchemy metadata
await conn.execute(
    text(f"CREATE SEQUENCE IF NOT EXISTS {TEST_TENANT_SCHEMA}.member_number_seq START 1")
)
await conn.execute(
    text(f"CREATE SEQUENCE IF NOT EXISTS {TEST_TENANT_SCHEMA}.loan_number_seq START 1")
)
```

- [ ] **Step 2: Run the full test suite**

```bash
pytest -x -q
```

Expected: all existing tests pass, no import errors, no new failures.

- [ ] **Step 3: Verify credit models are included in Base.metadata**

```bash
python -c "
from app.core.db import Base
import app.modules.credit.models
tables = [t for t in Base.metadata.tables if 'loan' in t]
print(sorted(tables))
"
```

Expected output (order may vary):
```
['loan_applications', 'loan_installments', 'loan_products', 'loan_repayments', 'loans']
```

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test: register credit models in conftest.py; create loan_number_seq for test schema"
```

---

## Verification Criteria

Run all of the following before marking this sub-plan complete:

```bash
# 1. Migration round-trip
docker compose exec api alembic -c alembic/tenant/env.py upgrade head
docker compose exec api alembic -c alembic/tenant/env.py downgrade 009
docker compose exec api alembic -c alembic/tenant/env.py upgrade head

# 2. Targeted new tests
pytest tests/modules/ledger/test_service.py::test_post_journal_entry_stores_sub_ledger_fields -v
pytest tests/modules/savings/test_service.py::test_savings_transaction_accepts_external_credit_type -v

# 3. No regressions in touched modules
pytest tests/modules/ledger/ tests/modules/savings/ -v

# 4. Full suite clean
pytest -x -q
```

All commands must exit 0.
