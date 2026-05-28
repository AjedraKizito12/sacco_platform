# Reporting Sub-Plan 01: Module Skeleton

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the reporting module skeleton: Alembic migration (6 tables), all 6 SQLAlchemy models, `_base.py` PDF/CSV rendering utilities, and the `api.py` router stub with all endpoint signatures.

**Architecture:** All reporting tables live in the tenant schema (no `schema=`). `ReportRun` is the audit record for each nightly materialization job. Five summary tables are truncated and repopulated on each run. `_base.py` holds the shared rendering utilities used by all five service classes.

**Tech Stack:** SQLAlchemy 2.0 async, Alembic, FastAPI, WeasyPrint, Jinja2, Python stdlib `csv`

**Spec:** `docs/superpowers/specs/2026-05-28-reporting-design.md`

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `alembic/tenant/versions/013_reporting_tables.py` | Create | Alembic migration: 6 tables |
| `app/modules/reporting/__init__.py` | Create | Empty package marker |
| `app/modules/reporting/models.py` | Create | ReportRun + 5 summary table models |
| `app/modules/reporting/schemas.py` | Create | Pydantic response types for all 5 reports |
| `app/modules/reporting/_base.py` | Create | render_pdf() and render_csv() utilities |
| `app/modules/reporting/api.py` | Create | FastAPI router with all endpoint stubs |
| `app/modules/reporting/services/__init__.py` | Create | Empty package marker |
| `app/modules/reporting/templates/` | Create | Directory (empty, templates added in sub-plans 02–06) |
| `app/main.py` | Modify | Register reporting router |
| `tests/conftest.py` | Modify | Import reporting models in `test_engine` fixture |
| `tests/modules/reporting/__init__.py` | Create | Empty package marker |

---

### Task 1: Alembic migration — 6 reporting tables

**Files:**
- Create: `alembic/tenant/versions/013_reporting_tables.py`

- [ ] **Step 1: Write the migration**

```python
# alembic/tenant/versions/013_reporting_tables.py
"""Reporting module: report_runs + 5 summary tables.

Revision: 013
Depends on: 012
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── report_runs ───────────────────────────────────────────────────────────
    op.create_table(
        "report_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("report_type", sa.Text(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'failed')",
            name="ck_rr_status",
        ),
        sa.CheckConstraint(
            "report_type IN ('trial_balance', 'loan_portfolio', 'income_statement', 'savings_statement', 'fee_collection')",
            name="ck_rr_report_type",
        ),
    )
    op.create_index(
        "ix_rr_type_date",
        "report_runs",
        ["report_type", sa.text("as_of_date DESC")],
    )

    # ── report_trial_balance_lines ────────────────────────────────────────────
    op.create_table(
        "report_trial_balance_lines",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("report_run_id", sa.UUID(), sa.ForeignKey("report_runs.id", name="fk_rtbl_run"), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("account_code", sa.Text(), nullable=False),
        sa.Column("account_name", sa.Text(), nullable=False),
        sa.Column("account_type", sa.Text(), nullable=False),
        sa.Column("debit_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("credit_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("balance", sa.Numeric(19, 4), nullable=False),
    )
    op.create_index("ix_rtbl_run_id", "report_trial_balance_lines", ["report_run_id"])

    # ── report_loan_portfolio_rows ────────────────────────────────────────────
    op.create_table(
        "report_loan_portfolio_rows",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("report_run_id", sa.UUID(), sa.ForeignKey("report_runs.id", name="fk_rlpr_run"), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("loan_id", sa.UUID(), nullable=False),
        sa.Column("loan_reference", sa.Text(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=False),
        sa.Column("disbursed_at", sa.Date(), nullable=False),
        sa.Column("maturity_date", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("outstanding_principal", sa.Numeric(19, 4), nullable=False),
        sa.Column("accrued_interest", sa.Numeric(19, 4), nullable=False),
        sa.Column("total_written_off", sa.Numeric(19, 4), nullable=False),
        sa.Column("days_in_arrears", sa.Integer(), nullable=False),
        sa.Column("aging_bucket", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "aging_bucket IN ('current', '1_30', '31_60', '61_90', '90_plus')",
            name="ck_rlpr_aging_bucket",
        ),
    )
    op.create_index("ix_rlpr_run_id", "report_loan_portfolio_rows", ["report_run_id"])

    # ── report_income_statement_lines ─────────────────────────────────────────
    op.create_table(
        "report_income_statement_lines",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("report_run_id", sa.UUID(), sa.ForeignKey("report_runs.id", name="fk_risl_run"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("account_code", sa.Text(), nullable=False),
        sa.Column("account_name", sa.Text(), nullable=False),
        sa.Column("account_type", sa.Text(), nullable=False),
        sa.Column("debit_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("credit_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("net_movement", sa.Numeric(19, 4), nullable=False),
    )
    op.create_index("ix_risl_run_id", "report_income_statement_lines", ["report_run_id"])

    # ── report_savings_statement_lines ────────────────────────────────────────
    op.create_table(
        "report_savings_statement_lines",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("report_run_id", sa.UUID(), sa.ForeignKey("report_runs.id", name="fk_rssl_run"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("savings_account_id", sa.UUID(), nullable=False),
        sa.Column("member_id", sa.UUID(), nullable=False),
        sa.Column("posted_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("transaction_type", sa.Text(), nullable=False),
        sa.Column("narration", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("running_balance", sa.Numeric(19, 4), nullable=False),
    )
    op.create_index("ix_rssl_run_id", "report_savings_statement_lines", ["report_run_id"])

    # ── report_fee_collection_rows ────────────────────────────────────────────
    op.create_table(
        "report_fee_collection_rows",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("report_run_id", sa.UUID(), sa.ForeignKey("report_runs.id", name="fk_rfcr_run"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("fee_type_id", sa.UUID(), nullable=False),
        sa.Column("fee_type_name", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=False),
        sa.Column("assessed_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("collected_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("outstanding_total", sa.Numeric(19, 4), nullable=False),
        sa.Column("waived_total", sa.Numeric(19, 4), nullable=False),
    )
    op.create_index("ix_rfcr_run_id", "report_fee_collection_rows", ["report_run_id"])


def downgrade() -> None:
    op.drop_table("report_fee_collection_rows")
    op.drop_table("report_savings_statement_lines")
    op.drop_table("report_income_statement_lines")
    op.drop_table("report_loan_portfolio_rows")
    op.drop_table("report_trial_balance_lines")
    op.drop_index("ix_rr_type_date", "report_runs")
    op.drop_table("report_runs")
```

- [ ] **Step 2: Verify migration runs**

```bash
# No actual alembic run needed — tables created via Base.metadata.create_all in tests.
# Just verify the file parses cleanly:
python -c "import alembic.tenant.versions.013_reporting_tables"
```

Expected: no import errors (note: this won't work as a module path; just eyeball the syntax).

- [ ] **Step 3: Commit**

```bash
git add alembic/tenant/versions/013_reporting_tables.py
git commit -m "feat(reporting): Alembic migration 013 — 6 reporting tables"
```

---

### Task 2: SQLAlchemy models

**Files:**
- Create: `app/modules/reporting/__init__.py`
- Create: `app/modules/reporting/models.py`
- Create: `app/modules/reporting/services/__init__.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Create package markers**

```python
# app/modules/reporting/__init__.py
# (empty)
```

```python
# app/modules/reporting/services/__init__.py
# (empty)
```

- [ ] **Step 2: Write the models**

```python
# app/modules/reporting/models.py
"""SQLAlchemy models for the reporting module.

ReportRun — audit record for each nightly materialization job.
Five summary tables — truncated and repopulated on each run.
No schema= on any model: resolved at runtime via SET LOCAL search_path.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    TIMESTAMP,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ReportRun(Base):
    """One row per (report_type, materialization run). Tracks status and timing."""

    __tablename__ = "report_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_type: Mapped[str] = mapped_column(Text, nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('running', 'done', 'failed')", name="ck_rr_status"),
        CheckConstraint(
            "report_type IN ('trial_balance', 'loan_portfolio', 'income_statement', 'savings_statement', 'fee_collection')",
            name="ck_rr_report_type",
        ),
        Index("ix_rr_type_date", "report_type", "as_of_date"),
    )


class ReportTrialBalanceLine(Base):
    """One row per GL account per trial balance run."""

    __tablename__ = "report_trial_balance_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_runs.id", name="fk_rtbl_run"), nullable=False
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_code: Mapped[str] = mapped_column(Text, nullable=False)
    account_name: Mapped[str] = mapped_column(Text, nullable=False)
    account_type: Mapped[str] = mapped_column(Text, nullable=False)
    debit_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    credit_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)

    __table_args__ = (Index("ix_rtbl_run_id", "report_run_id"),)


class ReportLoanPortfolioRow(Base):
    """One row per loan per portfolio run."""

    __tablename__ = "report_loan_portfolio_rows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_runs.id", name="fk_rlpr_run"), nullable=False
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    loan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    loan_reference: Mapped[str] = mapped_column(Text, nullable=False)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    product_name: Mapped[str] = mapped_column(Text, nullable=False)
    disbursed_at: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    outstanding_principal: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    accrued_interest: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    total_written_off: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    days_in_arrears: Mapped[int] = mapped_column(Integer, nullable=False)
    aging_bucket: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "aging_bucket IN ('current', '1_30', '31_60', '61_90', '90_plus')",
            name="ck_rlpr_aging_bucket",
        ),
        Index("ix_rlpr_run_id", "report_run_id"),
    )


class ReportIncomeStatementLine(Base):
    """One row per income/expense GL account per income statement run."""

    __tablename__ = "report_income_statement_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_runs.id", name="fk_risl_run"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account_code: Mapped[str] = mapped_column(Text, nullable=False)
    account_name: Mapped[str] = mapped_column(Text, nullable=False)
    account_type: Mapped[str] = mapped_column(Text, nullable=False)
    debit_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    credit_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    net_movement: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)

    __table_args__ = (Index("ix_risl_run_id", "report_run_id"),)


class ReportSavingsStatementLine(Base):
    """One row per savings transaction per savings statement run."""

    __tablename__ = "report_savings_statement_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_runs.id", name="fk_rssl_run"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    savings_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    posted_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    transaction_type: Mapped[str] = mapped_column(Text, nullable=False)
    narration: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    running_balance: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)

    __table_args__ = (Index("ix_rssl_run_id", "report_run_id"),)


class ReportFeeCollectionRow(Base):
    """One row per fee type per fee collection run."""

    __tablename__ = "report_fee_collection_rows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_runs.id", name="fk_rfcr_run"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    fee_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    fee_type_name: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    assessed_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    collected_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    outstanding_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)
    waived_total: Mapped[Decimal] = mapped_column(Numeric(19, 4), nullable=False)

    __table_args__ = (Index("ix_rfcr_run_id", "report_run_id"),)
```

- [ ] **Step 3: Register models in conftest.py**

In `tests/conftest.py`, add this import inside the `test_engine` fixture body, alongside the other model imports:

```python
    import app.modules.reporting.models  # noqa: F401 — registers reporting tables in Base.metadata
```

The import goes at the end of the existing block of `import app.modules.*.models` lines (around line 53).

- [ ] **Step 4: Run tests to verify no import errors**

```bash
cd /home/liam/projects/sacco-platform
pytest tests/conftest.py -x -q 2>&1 | head -20
```

Expected: collection passes (conftest.py has no tests itself, just fixtures).

Actually run a quick sanity check:

```bash
pytest tests/modules/credit/test_api.py::test_list_products -x -q
```

Expected: PASSED (existing test still works with new models registered).

- [ ] **Step 5: Commit**

```bash
git add app/modules/reporting/__init__.py app/modules/reporting/models.py app/modules/reporting/services/__init__.py tests/conftest.py
git commit -m "feat(reporting): SQLAlchemy models — ReportRun + 5 summary tables"
```

---

### Task 3: Pydantic schemas

**Files:**
- Create: `app/modules/reporting/schemas.py`

- [ ] **Step 1: Write the schemas**

```python
# app/modules/reporting/schemas.py
"""Pydantic response schemas for the reporting module."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# ── ReportRun ──────────────────────────────────────────────────────────────────

class ReportRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    report_type: str
    as_of_date: date
    status: str
    started_at: datetime
    completed_at: datetime | None
    error_detail: str | None


# ── Trial Balance ──────────────────────────────────────────────────────────────

class TrialBalanceLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: str
    debit_total: Decimal
    credit_total: Decimal
    balance: Decimal


class TrialBalanceOut(BaseModel):
    as_of_date: date
    generated_at: datetime
    lines: list[TrialBalanceLineOut]


# ── Loan Portfolio ─────────────────────────────────────────────────────────────

class LoanPortfolioRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    loan_id: uuid.UUID
    loan_reference: str
    member_id: uuid.UUID
    product_name: str
    disbursed_at: date
    maturity_date: date | None
    status: str
    outstanding_principal: Decimal
    accrued_interest: Decimal
    total_written_off: Decimal
    days_in_arrears: int
    aging_bucket: str


class LoanPortfolioOut(BaseModel):
    as_of_date: date
    generated_at: datetime
    rows: list[LoanPortfolioRowOut]


# ── Income Statement ───────────────────────────────────────────────────────────

class IncomeStatementLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_id: uuid.UUID
    account_code: str
    account_name: str
    account_type: str
    debit_total: Decimal
    credit_total: Decimal
    net_movement: Decimal


class IncomeStatementOut(BaseModel):
    period_start: date
    period_end: date
    generated_at: datetime
    lines: list[IncomeStatementLineOut]


# ── Savings Statement ──────────────────────────────────────────────────────────

class SavingsStatementLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    savings_account_id: uuid.UUID
    member_id: uuid.UUID
    posted_at: datetime
    transaction_type: str
    narration: str | None
    amount: Decimal
    running_balance: Decimal


class SavingsStatementOut(BaseModel):
    member_id: uuid.UUID
    period_start: date
    period_end: date
    generated_at: datetime
    lines: list[SavingsStatementLineOut]


# ── Fee Collection ─────────────────────────────────────────────────────────────

class FeeCollectionRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fee_type_id: uuid.UUID
    fee_type_name: str
    target_type: str
    assessed_total: Decimal
    collected_total: Decimal
    outstanding_total: Decimal
    waived_total: Decimal


class FeeCollectionOut(BaseModel):
    period_start: date
    period_end: date
    generated_at: datetime
    rows: list[FeeCollectionRowOut]
```

- [ ] **Step 2: Verify schemas import cleanly**

```bash
python -c "from app.modules.reporting.schemas import TrialBalanceOut, LoanPortfolioOut, IncomeStatementOut, SavingsStatementOut, FeeCollectionOut, ReportRunOut; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/modules/reporting/schemas.py
git commit -m "feat(reporting): Pydantic schemas for all 5 report types"
```

---

### Task 4: `_base.py` — PDF and CSV rendering utilities

**Files:**
- Create: `app/modules/reporting/_base.py`
- Create: `app/modules/reporting/templates/` (directory placeholder)

- [ ] **Step 1: Write `_base.py`**

```python
# app/modules/reporting/_base.py
"""Shared PDF and CSV rendering utilities for the reporting module.

render_pdf(template_name, context) -> bytes
    Renders a Jinja2 HTML template with WeasyPrint. Templates live in
    app/modules/reporting/templates/<template_name>.

render_csv(headers, rows) -> bytes
    Renders a list of rows as UTF-8 CSV bytes using Python stdlib csv.
    Returns bytes with BOM so Excel opens it without encoding prompts.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def render_pdf(template_name: str, context: dict) -> bytes:
    """Render a Jinja2 HTML template to PDF bytes via WeasyPrint.

    Args:
        template_name: Filename inside app/modules/reporting/templates/
                       e.g. "trial_balance.html"
        context: Dict passed to template.render(**context)

    Returns:
        PDF bytes.
    """
    import jinja2  # noqa: PLC0415 — optional dep, imported lazily
    import weasyprint  # noqa: PLC0415 — optional dep, imported lazily

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template(template_name)
    html_str = template.render(**context)
    pdf_bytes: bytes = weasyprint.HTML(string=html_str).write_pdf()
    return pdf_bytes


def render_csv(headers: list[str], rows: list[list]) -> bytes:
    """Render headers + rows as UTF-8-BOM CSV bytes.

    Args:
        headers: Column header strings, e.g. ["Account Code", "Account Name", ...]
        rows: List of rows; each row is a list of values (str/Decimal/int/date).

    Returns:
        UTF-8 BOM-prefixed CSV bytes. BOM makes Excel auto-detect UTF-8.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([str(v) if v is not None else "" for v in row])
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")
```

- [ ] **Step 2: Create template directory placeholder**

Create an empty `.gitkeep` file so the directory is tracked:

```bash
mkdir -p app/modules/reporting/templates
touch app/modules/reporting/templates/.gitkeep
```

- [ ] **Step 3: Write a unit test for render_csv**

```python
# tests/modules/reporting/test_base.py
"""Unit tests for _base.py rendering utilities."""
from __future__ import annotations

import csv
import io

import pytest

from app.modules.reporting._base import render_csv


def test_render_csv_headers_and_rows():
    headers = ["Code", "Name", "Balance"]
    rows = [["1000", "Cash", "5000.00"], ["2000", "Loans", "120000.00"]]
    result = render_csv(headers, rows)

    # BOM prefix
    assert result[:3] == b"\xef\xbb\xbf"

    # Valid CSV
    text = result.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))
    assert reader[0] == headers
    assert reader[1] == ["1000", "Cash", "5000.00"]
    assert reader[2] == ["2000", "Loans", "120000.00"]


def test_render_csv_none_values_become_empty_string():
    result = render_csv(["A", "B"], [[None, "value"]])
    text = result.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))
    assert reader[1] == ["", "value"]
```

- [ ] **Step 4: Run the test**

```bash
pytest tests/modules/reporting/test_base.py -v
```

Expected:
```
PASSED tests/modules/reporting/test_base.py::test_render_csv_headers_and_rows
PASSED tests/modules/reporting/test_base.py::test_render_csv_none_values_become_empty_string
```

- [ ] **Step 5: Commit**

```bash
git add app/modules/reporting/_base.py app/modules/reporting/templates/.gitkeep tests/modules/reporting/__init__.py tests/modules/reporting/test_base.py
git commit -m "feat(reporting): _base.py PDF/CSV rendering utilities + unit tests"
```

---

### Task 5: API router stub + wire into main.py

**Files:**
- Create: `app/modules/reporting/api.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write the router stub**

Each endpoint raises `501 Not Implemented` as a placeholder. Sub-plans 02–06 replace these stubs with real implementations.

```python
# app/modules/reporting/api.py
"""FastAPI router for the reporting module.

All endpoints read from pre-materialized summary tables.
Materialization happens nightly via Celery beat tasks (beat.py).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, UTC
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.modules.reporting.models import (
    ReportFeeCollectionRow,
    ReportIncomeStatementLine,
    ReportLoanPortfolioRow,
    ReportRun,
    ReportSavingsStatementLine,
    ReportTrialBalanceLine,
)
from app.modules.reporting.schemas import (
    FeeCollectionOut,
    FeeCollectionRowOut,
    IncomeStatementLineOut,
    IncomeStatementOut,
    LoanPortfolioOut,
    LoanPortfolioRowOut,
    ReportRunOut,
    SavingsStatementLineOut,
    SavingsStatementOut,
    TrialBalanceLineOut,
    TrialBalanceOut,
)

router = APIRouter(prefix="/reporting", tags=["reporting"])
Session = Annotated[AsyncSession, Depends(get_tenant_session)]


async def _latest_run(session: AsyncSession, report_type: str, as_of: date | None) -> ReportRun:
    """Fetch the most recent successful ReportRun for a report type.

    If as_of is provided, fetches the run for that specific date.
    Raises 404 with last_successful_run info if no run found.
    """
    q = (
        select(ReportRun)
        .where(ReportRun.report_type == report_type, ReportRun.status == "done")
        .order_by(ReportRun.as_of_date.desc())
        .limit(1)
    )
    if as_of is not None:
        q = q.where(ReportRun.as_of_date == as_of)
    run = await session.scalar(q)
    if run is None:
        # Find last successful run for error body.
        last = await session.scalar(
            select(ReportRun)
            .where(ReportRun.report_type == report_type, ReportRun.status == "done")
            .order_by(ReportRun.as_of_date.desc())
            .limit(1)
        )
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"No materialized {report_type} data for requested date",
                "last_successful_run": last.completed_at.isoformat() if last else None,
            },
        )
    return run


@router.get("/trial-balance")
async def get_trial_balance(
    session: Session,
    as_of: date | None = Query(default=None),
    format: str = Query(default="json", pattern="^(json|pdf|csv)$"),
):
    """Trial balance as of a date. Defaults to latest successful run."""
    run = await _latest_run(session, "trial_balance", as_of)
    lines = list(
        (
            await session.execute(
                select(ReportTrialBalanceLine)
                .where(ReportTrialBalanceLine.report_run_id == run.id)
                .order_by(ReportTrialBalanceLine.account_code)
            )
        )
        .scalars()
        .all()
    )

    if format == "json":
        return TrialBalanceOut(
            as_of_date=run.as_of_date,
            generated_at=datetime.now(tz=UTC),
            lines=[TrialBalanceLineOut.model_validate(ln) for ln in lines],
        )
    if format == "pdf":
        from app.modules.reporting._base import render_pdf  # noqa: PLC0415
        pdf = render_pdf("trial_balance.html", {
            "run": run, "lines": lines, "generated_at": datetime.now(tz=UTC),
        })
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="trial-balance-{run.as_of_date}.pdf"'},
        )
    # csv
    from app.modules.reporting._base import render_csv  # noqa: PLC0415
    headers = ["Account Code", "Account Name", "Account Type", "Debit Total", "Credit Total", "Balance"]
    rows = [[ln.account_code, ln.account_name, ln.account_type, ln.debit_total, ln.credit_total, ln.balance] for ln in lines]
    return Response(
        content=render_csv(headers, rows),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="trial-balance-{run.as_of_date}.csv"'},
    )


@router.get("/loan-portfolio")
async def get_loan_portfolio(
    session: Session,
    as_of: date | None = Query(default=None),
    status: str = Query(default="all", pattern="^(all|disbursed|in_arrears|written_off)$"),
    format: str = Query(default="json", pattern="^(json|pdf|csv)$"),
):
    """Loan portfolio as of a date."""
    run = await _latest_run(session, "loan_portfolio", as_of)
    q = (
        select(ReportLoanPortfolioRow)
        .where(ReportLoanPortfolioRow.report_run_id == run.id)
        .order_by(ReportLoanPortfolioRow.loan_reference)
    )
    if status != "all":
        q = q.where(ReportLoanPortfolioRow.status == status)
    rows = list((await session.execute(q)).scalars().all())

    if format == "json":
        return LoanPortfolioOut(
            as_of_date=run.as_of_date,
            generated_at=datetime.now(tz=UTC),
            rows=[LoanPortfolioRowOut.model_validate(r) for r in rows],
        )
    if format == "pdf":
        from app.modules.reporting._base import render_pdf  # noqa: PLC0415
        pdf = render_pdf("loan_portfolio.html", {"run": run, "rows": rows, "generated_at": datetime.now(tz=UTC)})
        return Response(content=pdf, media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="loan-portfolio-{run.as_of_date}.pdf"'})
    from app.modules.reporting._base import render_csv  # noqa: PLC0415
    headers = ["Loan Ref", "Member ID", "Product", "Disbursed At", "Maturity Date", "Status",
               "Outstanding Principal", "Accrued Interest", "Total Written Off", "Days in Arrears", "Aging Bucket"]
    csv_rows = [[r.loan_reference, r.member_id, r.product_name, r.disbursed_at, r.maturity_date,
                 r.status, r.outstanding_principal, r.accrued_interest, r.total_written_off,
                 r.days_in_arrears, r.aging_bucket] for r in rows]
    return Response(content=render_csv(headers, csv_rows), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="loan-portfolio-{run.as_of_date}.csv"'})


@router.get("/income-statement")
async def get_income_statement(
    session: Session,
    from_date: date = Query(...),
    to_date: date = Query(...),
    format: str = Query(default="json", pattern="^(json|pdf|csv)$"),
):
    """Income statement for a period. from_date and to_date are required."""
    # Find run whose period_start == from_date and period_end == to_date.
    run = await session.scalar(
        select(ReportRun)
        .where(
            ReportRun.report_type == "income_statement",
            ReportRun.status == "done",
            ReportRun.as_of_date == to_date,
        )
        .order_by(ReportRun.as_of_date.desc())
        .limit(1)
    )
    if run is None:
        last = await session.scalar(
            select(ReportRun)
            .where(ReportRun.report_type == "income_statement", ReportRun.status == "done")
            .order_by(ReportRun.as_of_date.desc())
            .limit(1)
        )
        raise HTTPException(
            status_code=404,
            detail={
                "message": "No materialized income statement data for requested period",
                "last_successful_run": last.completed_at.isoformat() if last else None,
            },
        )
    lines_q = (
        select(ReportIncomeStatementLine)
        .where(
            ReportIncomeStatementLine.report_run_id == run.id,
            ReportIncomeStatementLine.period_start >= from_date,
            ReportIncomeStatementLine.period_end <= to_date,
        )
        .order_by(ReportIncomeStatementLine.account_code)
    )
    lines = list((await session.execute(lines_q)).scalars().all())

    if format == "json":
        return IncomeStatementOut(
            period_start=from_date, period_end=to_date,
            generated_at=datetime.now(tz=UTC),
            lines=[IncomeStatementLineOut.model_validate(ln) for ln in lines],
        )
    if format == "pdf":
        from app.modules.reporting._base import render_pdf  # noqa: PLC0415
        pdf = render_pdf("income_statement.html", {"run": run, "lines": lines, "from_date": from_date, "to_date": to_date, "generated_at": datetime.now(tz=UTC)})
        return Response(content=pdf, media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="income-statement-{from_date}-{to_date}.pdf"'})
    from app.modules.reporting._base import render_csv  # noqa: PLC0415
    headers = ["Account Code", "Account Name", "Account Type", "Debit Total", "Credit Total", "Net Movement"]
    csv_rows = [[ln.account_code, ln.account_name, ln.account_type, ln.debit_total, ln.credit_total, ln.net_movement] for ln in lines]
    return Response(content=render_csv(headers, csv_rows), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="income-statement-{from_date}-{to_date}.csv"'})


@router.get("/savings-statement")
async def get_savings_statement(
    session: Session,
    member_id: uuid.UUID = Query(...),
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    format: str = Query(default="json", pattern="^(json|pdf|csv)$"),
):
    """Savings statement for a member. member_id is required."""
    # Latest run that covers the period.
    run = await session.scalar(
        select(ReportRun)
        .where(ReportRun.report_type == "savings_statement", ReportRun.status == "done")
        .order_by(ReportRun.as_of_date.desc())
        .limit(1)
    )
    if run is None:
        raise HTTPException(status_code=404, detail={"message": "No materialized savings statement data", "last_successful_run": None})

    q = (
        select(ReportSavingsStatementLine)
        .where(
            ReportSavingsStatementLine.report_run_id == run.id,
            ReportSavingsStatementLine.member_id == member_id,
        )
        .order_by(ReportSavingsStatementLine.posted_at)
    )
    if from_date is not None:
        q = q.where(ReportSavingsStatementLine.period_start >= from_date)
    if to_date is not None:
        q = q.where(ReportSavingsStatementLine.period_end <= to_date)
    lines = list((await session.execute(q)).scalars().all())

    effective_from = from_date or run.as_of_date
    effective_to = to_date or run.as_of_date

    if format == "json":
        return SavingsStatementOut(
            member_id=member_id, period_start=effective_from, period_end=effective_to,
            generated_at=datetime.now(tz=UTC),
            lines=[SavingsStatementLineOut.model_validate(ln) for ln in lines],
        )
    if format == "pdf":
        from app.modules.reporting._base import render_pdf  # noqa: PLC0415
        pdf = render_pdf("savings_statement.html", {"run": run, "lines": lines, "member_id": member_id, "from_date": effective_from, "to_date": effective_to, "generated_at": datetime.now(tz=UTC)})
        return Response(content=pdf, media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="savings-statement-{member_id}-{effective_to}.pdf"'})
    from app.modules.reporting._base import render_csv  # noqa: PLC0415
    headers = ["Posted At", "Transaction Type", "Narration", "Amount", "Running Balance"]
    csv_rows = [[ln.posted_at, ln.transaction_type, ln.narration, ln.amount, ln.running_balance] for ln in lines]
    return Response(content=render_csv(headers, csv_rows), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="savings-statement-{member_id}-{effective_to}.csv"'})


@router.get("/fee-collection")
async def get_fee_collection(
    session: Session,
    from_date: date = Query(...),
    to_date: date = Query(...),
    fee_type_id: uuid.UUID | None = Query(default=None),
    format: str = Query(default="json", pattern="^(json|pdf|csv)$"),
):
    """Fee collection summary for a period. from_date and to_date are required."""
    run = await session.scalar(
        select(ReportRun)
        .where(
            ReportRun.report_type == "fee_collection",
            ReportRun.status == "done",
            ReportRun.as_of_date == to_date,
        )
        .order_by(ReportRun.as_of_date.desc())
        .limit(1)
    )
    if run is None:
        last = await session.scalar(
            select(ReportRun)
            .where(ReportRun.report_type == "fee_collection", ReportRun.status == "done")
            .order_by(ReportRun.as_of_date.desc())
            .limit(1)
        )
        raise HTTPException(
            status_code=404,
            detail={"message": "No materialized fee collection data for requested period", "last_successful_run": last.completed_at.isoformat() if last else None},
        )
    q = (
        select(ReportFeeCollectionRow)
        .where(ReportFeeCollectionRow.report_run_id == run.id)
        .order_by(ReportFeeCollectionRow.fee_type_name)
    )
    if fee_type_id is not None:
        q = q.where(ReportFeeCollectionRow.fee_type_id == fee_type_id)
    rows = list((await session.execute(q)).scalars().all())

    if format == "json":
        return FeeCollectionOut(
            period_start=from_date, period_end=to_date,
            generated_at=datetime.now(tz=UTC),
            rows=[FeeCollectionRowOut.model_validate(r) for r in rows],
        )
    if format == "pdf":
        from app.modules.reporting._base import render_pdf  # noqa: PLC0415
        pdf = render_pdf("fee_collection.html", {"run": run, "rows": rows, "from_date": from_date, "to_date": to_date, "generated_at": datetime.now(tz=UTC)})
        return Response(content=pdf, media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="fee-collection-{from_date}-{to_date}.pdf"'})
    from app.modules.reporting._base import render_csv  # noqa: PLC0415
    headers = ["Fee Type", "Target Type", "Assessed Total", "Collected Total", "Outstanding Total", "Waived Total"]
    csv_rows = [[r.fee_type_name, r.target_type, r.assessed_total, r.collected_total, r.outstanding_total, r.waived_total] for r in rows]
    return Response(content=render_csv(headers, csv_rows), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="fee-collection-{from_date}-{to_date}.csv"'})


@router.get("/runs", response_model=list[ReportRunOut])
async def list_report_runs(
    session: Session,
    report_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
) -> list[ReportRunOut]:
    """List recent report runs. Optionally filter by report_type."""
    q = select(ReportRun).order_by(ReportRun.started_at.desc()).limit(limit)
    if report_type is not None:
        q = q.where(ReportRun.report_type == report_type)
    runs = list((await session.execute(q)).scalars().all())
    return [ReportRunOut.model_validate(r) for r in runs]
```

- [ ] **Step 2: Register router in main.py**

In `app/main.py`, add after the other router imports:

```python
from app.modules.reporting.api import router as reporting_router
```

And add after `app.include_router(fees_router)`:

```python
app.include_router(reporting_router)
```

- [ ] **Step 3: Run a quick sanity check**

```bash
pytest tests/modules/credit/test_api.py::test_list_products -x -q
```

Expected: PASSED (app still starts correctly with the new router).

- [ ] **Step 4: Commit**

```bash
git add app/modules/reporting/api.py app/main.py
git commit -m "feat(reporting): API router with all endpoint stubs wired into main.py"
```

---

## Self-Review Checklist

- [x] Spec coverage: 6 tables in migration ✓, all models defined ✓, all 5 Pydantic schemas ✓, render_pdf + render_csv in _base.py ✓, all 6 API endpoints ✓ (trial-balance, loan-portfolio, income-statement, savings-statement, fee-collection, runs), format dispatch in each endpoint ✓, 404 with last_successful_run ✓
- [x] No placeholders: all code is complete
- [x] Type consistency: `ReportRun`, `ReportTrialBalanceLine`, etc. names match across models/schemas/api
- [x] conftest.py update: reporting models registered so `Base.metadata.create_all` creates the tables in tests
