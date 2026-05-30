# Sub-plan 01 — Migration and Models

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans`.

**Goal:** Add migration 012 with all v1b tables, extend existing models, and wire new
models into conftest so subsequent sub-plans can test against them.

**Architecture:** Follow the exact pattern of `010_credit_tables.py`. All new tables live in
the tenant schema (no `schema=` argument). New models are added to `app/modules/credit/models.py`.

**Tech Stack:** SQLAlchemy 2.0, Alembic, PostgreSQL 16, pytest-asyncio

---

## Required Reading

- `alembic/tenant/versions/011_la_status_disbursed.py` — migration boilerplate
- `alembic/tenant/versions/010_credit_tables.py` — table creation pattern
- `app/modules/credit/models.py` — existing models to extend
- `tests/conftest.py` — model import pattern

---

## Task 1: Create Migration 012

**Files:**
- Create: `alembic/tenant/versions/012_credit_v1b_tables.py`

- [ ] **Step 1: Create the migration file**

```python
# alembic/tenant/versions/012_credit_v1b_tables.py
"""Credit v1b: guarantors, guarantor liens, restructurings, payroll tables;
add required_guarantors to loan_products; add restructuring_id + is_superseded
to loan_installments; add 'written_off' → 'in_arrears' recovery transition.

Revision: 012
Depends on: 011
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── loan_products: add required_guarantors ────────────────────────────────
    op.add_column(
        "loan_products",
        sa.Column("required_guarantors", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_lp_required_guarantors",
        "loan_products",
        "required_guarantors >= 0",
    )

    # ── loan_guarantors ───────────────────────────────────────────────────────
    op.create_table(
        "loan_guarantors",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("loan_application_id", sa.UUID(), sa.ForeignKey("loan_applications.id", name="fk_lg_application"), nullable=False),
        sa.Column("loan_id", sa.UUID(), sa.ForeignKey("loans.id", name="fk_lg_loan"), nullable=True),
        sa.Column("guarantor_member_id", sa.UUID(), nullable=False),
        sa.Column("guaranteed_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="nominated"),
        sa.Column("consented_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("released_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_lg_idempotency_key"),
        sa.UniqueConstraint("loan_application_id", "guarantor_member_id", name="uq_lg_application_member"),
        sa.CheckConstraint(
            "status IN ('nominated', 'accepted', 'declined', 'released')",
            name="ck_lg_status",
        ),
        sa.CheckConstraint("guaranteed_amount > 0", name="ck_lg_guaranteed_amount"),
    )
    op.create_index("ix_lg_loan_application_id", "loan_guarantors", ["loan_application_id"])
    op.create_index("ix_lg_guarantor_member_id", "loan_guarantors", ["guarantor_member_id"])
    op.create_index("ix_lg_loan_id", "loan_guarantors", ["loan_id"])

    # ── loan_restructurings (before loan_installments FK) ─────────────────────
    op.create_table(
        "loan_restructurings",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("loan_id", sa.UUID(), sa.ForeignKey("loans.id", name="fk_lr_loan"), nullable=False),
        sa.Column("restructuring_type", sa.Text(), nullable=False),
        sa.Column("periods_added", sa.Integer(), nullable=False),
        sa.Column("new_term_periods", sa.Integer(), nullable=False),
        sa.Column("new_maturity_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("executed_by", sa.UUID(), nullable=False),
        sa.Column("executed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_lrs_idempotency_key"),
        sa.CheckConstraint(
            "restructuring_type IN ('term_extension', 'payment_holiday')",
            name="ck_lrs_type",
        ),
        sa.CheckConstraint("periods_added >= 1", name="ck_lrs_periods_added"),
    )
    op.create_index("ix_lrs_loan_id", "loan_restructurings", ["loan_id"])

    # ── loan_installments: add restructuring columns ──────────────────────────
    op.add_column(
        "loan_installments",
        sa.Column("restructuring_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "loan_installments",
        sa.Column("is_superseded", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_foreign_key(
        "fk_li_restructuring",
        "loan_installments",
        "loan_restructurings",
        ["restructuring_id"],
        ["id"],
    )
    op.create_index("ix_li_restructuring_id", "loan_installments", ["restructuring_id"])
    op.create_index(
        "ix_li_loan_active",
        "loan_installments",
        ["loan_id"],
        postgresql_where=sa.text("NOT is_superseded"),
    )

    # ── loan_guarantor_liens ──────────────────────────────────────────────────
    op.create_table(
        "loan_guarantor_liens",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("loan_guarantor_id", sa.UUID(), sa.ForeignKey("loan_guarantors.id", name="fk_lgl_guarantor"), nullable=False),
        sa.Column("savings_account_id", sa.UUID(), nullable=False),
        sa.Column("original_lien", sa.Numeric(19, 4), nullable=False),
        sa.Column("current_lien", sa.Numeric(19, 4), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("original_lien > 0", name="ck_lgl_original_lien"),
        sa.CheckConstraint("current_lien >= 0", name="ck_lgl_current_lien"),
    )
    op.create_index("ix_lgl_loan_guarantor_id", "loan_guarantor_liens", ["loan_guarantor_id"])
    op.create_index(
        "ix_lgl_savings_account_active",
        "loan_guarantor_liens",
        ["savings_account_id", "is_active"],
        postgresql_where=sa.text("is_active = true"),
    )

    # ── payroll_batches ───────────────────────────────────────────────────────
    op.create_table(
        "payroll_batches",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("reference", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending_review"),
        sa.Column("submitted_by", sa.UUID(), nullable=False),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("approval_request_id", sa.UUID(), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("matched_rows", sa.Integer(), nullable=False),
        sa.Column("unmatched_rows", sa.Integer(), nullable=False),
        sa.Column("total_amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("source_format", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("reference", name="uq_pb_reference"),
        sa.UniqueConstraint("idempotency_key", name="uq_pb_idempotency_key"),
        sa.CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'applied')",
            name="ck_pb_status",
        ),
        sa.CheckConstraint("source_format IN ('csv', 'json')", name="ck_pb_source_format"),
    )

    # ── payroll_batch_lines ───────────────────────────────────────────────────
    op.create_table(
        "payroll_batch_lines",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("payroll_batch_id", sa.UUID(), sa.ForeignKey("payroll_batches.id", name="fk_pbl_batch"), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=True),
        sa.Column("raw_member_ref", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("loan_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="unmatched"),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("repayment_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('matched', 'unmatched', 'applied', 'error')",
            name="ck_pbl_status",
        ),
        sa.CheckConstraint("amount > 0", name="ck_pbl_amount"),
    )
    op.create_index("ix_pbl_payroll_batch_id", "payroll_batch_lines", ["payroll_batch_id"])
    op.create_index("ix_pbl_loan_id", "payroll_batch_lines", ["loan_id"])

    # ── payroll_batch_number_seq ──────────────────────────────────────────────
    op.execute("CREATE SEQUENCE IF NOT EXISTS payroll_batch_number_seq START 1")

    # ── loans: add 'in_arrears' as valid recovery target (already valid) ──────
    # loans.status CHECK already includes 'in_arrears' from migration 010.
    # No change needed.


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS payroll_batch_number_seq")
    op.drop_table("payroll_batch_lines")
    op.drop_table("payroll_batches")
    op.drop_index("ix_lgl_savings_account_active", "loan_guarantor_liens")
    op.drop_index("ix_lgl_loan_guarantor_id", "loan_guarantor_liens")
    op.drop_table("loan_guarantor_liens")
    op.drop_constraint("fk_li_restructuring", "loan_installments", type_="foreignkey")
    op.drop_index("ix_li_loan_active", "loan_installments")
    op.drop_index("ix_li_restructuring_id", "loan_installments")
    op.drop_column("loan_installments", "is_superseded")
    op.drop_column("loan_installments", "restructuring_id")
    op.drop_index("ix_lrs_loan_id", "loan_restructurings")
    op.drop_table("loan_restructurings")
    op.drop_index("ix_lg_loan_id", "loan_guarantors")
    op.drop_index("ix_lg_guarantor_member_id", "loan_guarantors")
    op.drop_index("ix_lg_loan_application_id", "loan_guarantors")
    op.drop_table("loan_guarantors")
    op.drop_constraint("ck_lp_required_guarantors", "loan_products", type_="check")
    op.drop_column("loan_products", "required_guarantors")
```

- [ ] **Step 2: Run migration against test DB**

```bash
venv/bin/alembic -c alembic/tenant/alembic.ini upgrade head
```

Expected: no errors, `Running upgrade 011 -> 012`.

- [ ] **Step 3: Commit**

```bash
git add alembic/tenant/versions/012_credit_v1b_tables.py
git commit -m "feat(credit): migration 012 — v1b tables (guarantors, restructurings, payroll)"
```

---

## Task 2: Add New SQLAlchemy Models

**Files:**
- Modify: `app/modules/credit/models.py`

- [ ] **Step 1: Add new model classes**

At the bottom of `app/modules/credit/models.py`, append the following five model classes.
Also add `required_guarantors` to `LoanProduct` and `restructuring_id`/`is_superseded` to `LoanInstallment`.

**2a — Extend `LoanProduct` (add after `write_off_threshold` field):**

```python
    required_guarantors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

Add to `LoanProduct.__table_args__`:
```python
        CheckConstraint("required_guarantors >= 0", name="ck_lp_required_guarantors"),
```

**2b — Extend `LoanInstallment` (add after `updated_at` field, before `__table_args__`):**

```python
    restructuring_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("loan_restructurings.id", name="fk_li_restructuring"),
        nullable=True,
    )
    is_superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

Add to `LoanInstallment.__table_args__`:
```python
        Index("ix_li_restructuring_id", "restructuring_id"),
```

**2c — New models (append to end of file):**

```python
class LoanGuarantor(AuditableMixin, Base):
    """One guarantor nomination per application. Carries through to the active loan."""

    __tablename__ = "loan_guarantors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loan_applications.id", name="fk_lg_application"), nullable=False
    )
    loan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loans.id", name="fk_lg_loan"), nullable=True
    )
    guarantor_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    guaranteed_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="nominated")
    consented_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_lg_idempotency_key"),
        UniqueConstraint("loan_application_id", "guarantor_member_id", name="uq_lg_application_member"),
        CheckConstraint("status IN ('nominated', 'accepted', 'declined', 'released')", name="ck_lg_status"),
        CheckConstraint("guaranteed_amount > 0", name="ck_lg_guaranteed_amount"),
        Index("ix_lg_loan_application_id", "loan_application_id"),
        Index("ix_lg_guarantor_member_id", "guarantor_member_id"),
        Index("ix_lg_loan_id", "loan_id"),
    )


class LoanGuarantorLien(Base):
    """Live lien against a guarantor's savings account. Append-only creation; current_lien updated in-place."""

    __tablename__ = "loan_guarantor_liens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_guarantor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loan_guarantors.id", name="fk_lgl_guarantor"), nullable=False
    )
    savings_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    original_lien: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    current_lien: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("original_lien > 0", name="ck_lgl_original_lien"),
        CheckConstraint("current_lien >= 0", name="ck_lgl_current_lien"),
        Index("ix_lgl_loan_guarantor_id", "loan_guarantor_id"),
        Index("ix_lgl_savings_account_active", "savings_account_id", "is_active"),
    )


class LoanRestructuring(Base):
    """One record per executed restructuring event. Append-only."""

    __tablename__ = "loan_restructurings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    loan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("loans.id", name="fk_lrs_loan"), nullable=False
    )
    restructuring_type: Mapped[str] = mapped_column(Text, nullable=False)
    periods_added: Mapped[int] = mapped_column(Integer, nullable=False)
    new_term_periods: Mapped[int] = mapped_column(Integer, nullable=False)
    new_maturity_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    executed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_lrs_idempotency_key"),
        CheckConstraint(
            "restructuring_type IN ('term_extension', 'payment_holiday')", name="ck_lrs_type"
        ),
        CheckConstraint("periods_added >= 1", name="ck_lrs_periods_added"),
        Index("ix_lrs_loan_id", "loan_id"),
    )


class PayrollBatch(AuditableMixin, Base):
    """One row per payroll batch submission."""

    __tablename__ = "payroll_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending_review")
    submitted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    unmatched_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    source_format: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("reference", name="uq_pb_reference"),
        UniqueConstraint("idempotency_key", name="uq_pb_idempotency_key"),
        CheckConstraint(
            "status IN ('pending_review', 'approved', 'rejected', 'applied')", name="ck_pb_status"
        ),
        CheckConstraint("source_format IN ('csv', 'json')", name="ck_pb_source_format"),
    )


class PayrollBatchLine(Base):
    """One row per member in a payroll batch."""

    __tablename__ = "payroll_batch_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payroll_batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payroll_batches.id", name="fk_pbl_batch"), nullable=False
    )
    member_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    raw_member_ref: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    loan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="unmatched")
    error_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    repayment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('matched', 'unmatched', 'applied', 'error')", name="ck_pbl_status"
        ),
        CheckConstraint("amount > 0", name="ck_pbl_amount"),
        Index("ix_pbl_payroll_batch_id", "payroll_batch_id"),
        Index("ix_pbl_loan_id", "loan_id"),
    )
```

- [ ] **Step 2: Verify no import errors**

```bash
venv/bin/python -c "from app.modules.credit.models import (
    LoanGuarantor, LoanGuarantorLien, LoanRestructuring, PayrollBatch, PayrollBatchLine
); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/modules/credit/models.py
git commit -m "feat(credit): add v1b SQLAlchemy models — guarantors, restructurings, payroll"
```

---

## Task 3: Update conftest.py

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Import new models in test_engine fixture**

In `tests/conftest.py`, inside the `test_engine` fixture (the session-scoped one),
add the following import after the existing `import app.modules.credit.models` line:

```python
    import app.modules.credit.models  # noqa: F401 — registers credit tables in Base.metadata
    # (already present — v1b models are in the same file, no new import needed)
```

Then add the payroll batch sequence creation inside the `async with engine.begin()` block,
after the `loan_number_seq` line:

```python
        await conn.execute(
            text(f"CREATE SEQUENCE IF NOT EXISTS {TEST_TENANT_SCHEMA}.payroll_batch_number_seq START 1")
        )
```

- [ ] **Step 2: Verify collection with no import errors**

```bash
venv/bin/pytest tests/modules/credit/ --collect-only -q 2>&1 | tail -5
```

Expected: no import errors; existing test count shown.

- [ ] **Step 3: Run existing credit tests to confirm no regressions**

```bash
venv/bin/pytest tests/modules/credit/test_service.py tests/modules/credit/test_schedule.py -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test(credit): wire v1b models + payroll sequence into conftest"
```

---

## Verification Criteria

```bash
# Migration runs cleanly
venv/bin/alembic -c alembic/tenant/alembic.ini upgrade head

# New models import without errors
venv/bin/python -c "
from app.modules.credit.models import (
    LoanProduct, LoanInstallment,
    LoanGuarantor, LoanGuarantorLien,
    LoanRestructuring, PayrollBatch, PayrollBatchLine,
)
print('All v1b models import OK')
"

# Test collection — no import errors
venv/bin/pytest tests/modules/credit/ --collect-only -q 2>&1 | tail -3

# Existing tests still pass
venv/bin/pytest tests/modules/credit/test_service.py tests/modules/credit/test_schedule.py -q
```
