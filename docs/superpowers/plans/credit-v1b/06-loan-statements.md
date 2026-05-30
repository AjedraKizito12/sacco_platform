# Credit v1b Sub-Plan 06 — Loan Statements

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `LoanStatementService` (JSON statement + WeasyPrint PDF) and wire two
statement API endpoints.

**Architecture:** Statement lines are assembled by querying `journal_lines`
(`sub_ledger_type='loan'`) and `fee_assessments` (`target_type='loan'`), ordered by
`posted_at`. Each line carries a `running_balance` computed by replay. PDF is rendered
from a Jinja2 HTML template via WeasyPrint.

**Tech Stack:** SQLAlchemy 2.0 async, Pydantic v2, FastAPI, Jinja2, WeasyPrint

**Prerequisite:** Sub-plans 01–05 complete. `weasyprint>=62.0` must be in `requirements.txt`.

---

## Required Reading

Before starting:
- `app/modules/ledger/models.py` — `JournalEntry` (`posted_at`), `JournalLine`
  (`sub_ledger_type`, `sub_ledger_id`, `debit_amount`, `credit_amount`)
- `app/modules/fees/models.py` — `FeeAssessment` (`target_type`, `target_id`, `assessed_at`,
  `amount`)
- `app/modules/credit/models.py` — `Loan`, `LoanRepayment`
- Design spec §9

---

## Task 1: Add WeasyPrint dependency

**Files:**
- Modify: `requirements.txt` (or `pyproject.toml` if that's the pinning file)

- [ ] **Step 1: Add weasyprint to requirements**

Open `requirements.txt` and add:

```
weasyprint>=62.0
```

- [ ] **Step 2: Install and verify**

```bash
pip install weasyprint>=62.0
python -c "import weasyprint; print(weasyprint.__version__)"
```

Expected: version string printed with no errors.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat(credit): add weasyprint>=62.0 for loan statement PDF rendering"
```

---

## Task 2: `LoanStatementService` — JSON statement

**Files:**
- Create: `app/modules/credit/services/statement.py`
- Create: `tests/modules/credit/test_statement_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/modules/credit/test_statement_service.py`:

```python
"""Tests for LoanStatementService — JSON statement and PDF rendering."""
from __future__ import annotations

import uuid
from datetime import date, datetime, UTC
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.modules.credit.services.statement import LoanStatementService, StatementLine


@pytest.fixture
async def loan_with_repayment(
    tenant_session,
    seeded_loan_product,
    db_member,
    db_savings_account,
    gl_accounts,
):
    """A disbursed loan that has one repayment posted, plus a fee assessment."""
    from app.modules.credit.models import Loan, LoanApplication, LoanRepayment
    from app.modules.fees.models import FeeAssessment
    from app.modules.ledger.models import JournalEntry, JournalLine

    app_obj = LoanApplication(
        loan_product_id=seeded_loan_product.id,
        member_id=db_member.id,
        requested_amount=Decimal("120000"),
        requested_term_periods=6,
        purpose="test statement",
        disbursement_destination="member_savings",
        disbursement_account_id=db_savings_account.id,
        status="disbursed",
        idempotency_key=str(uuid.uuid4()),
    )
    tenant_session.add(app_obj)

    loan = Loan(
        loan_reference=f"LN-STMT-{uuid.uuid4().hex[:6].upper()}",
        loan_application_id=app_obj.id,
        loan_product_id=seeded_loan_product.id,
        member_id=db_member.id,
        status="disbursed",
        principal_amount=Decimal("120000"),
        interest_method="flat",
        annual_interest_rate=Decimal("18"),
        repayment_frequency="monthly",
        term_periods=6,
        repayment_allocation="INTEREST_PRINCIPAL",
        disbursement_destination="member_savings",
        disbursement_account_id=db_savings_account.id,
        gl_principal_receivable_id=gl_accounts["principal_receivable"].id,
        gl_interest_receivable_id=gl_accounts["interest_receivable"].id,
        gl_interest_income_id=gl_accounts["interest_income"].id,
        gl_disbursement_account_id=gl_accounts["disbursement"].id,
        outstanding_principal=Decimal("100000"),
        total_paid_principal=Decimal("20000"),
        total_paid_interest=Decimal("1800"),
        disbursed_by=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        disbursed_at=datetime(2026, 1, 15, tzinfo=UTC),
        first_repayment_due=date(2026, 2, 15),
        maturity_date=date(2026, 7, 15),
        idempotency_key=str(uuid.uuid4()),
    )
    tenant_session.add(loan)
    await tenant_session.flush()

    # Disbursement journal entry (credit to receivable).
    disb_entry = JournalEntry(
        reference=f"LOAN-DISB-{loan.id}",
        description="Loan disbursement",
        posted_by=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        idempotency_key=f"disb-{loan.id}",
    )
    tenant_session.add(disb_entry)
    await tenant_session.flush()

    disb_line = JournalLine(
        journal_entry_id=disb_entry.id,
        account_id=gl_accounts["principal_receivable"].id,
        debit_amount=Decimal("120000"),
        credit_amount=Decimal("0"),
        sub_ledger_type="loan",
        sub_ledger_id=loan.id,
    )
    tenant_session.add(disb_line)

    # Repayment journal entry.
    rep_entry = JournalEntry(
        reference=f"LOAN-REP-{loan.id}-1",
        description="Repayment 1",
        posted_by=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        idempotency_key=f"rep-{loan.id}-1",
    )
    tenant_session.add(rep_entry)
    await tenant_session.flush()

    rep_line = JournalLine(
        journal_entry_id=rep_entry.id,
        account_id=gl_accounts["principal_receivable"].id,
        debit_amount=Decimal("0"),
        credit_amount=Decimal("21800"),
        sub_ledger_type="loan",
        sub_ledger_id=loan.id,
    )
    tenant_session.add(rep_line)

    await tenant_session.commit()
    await tenant_session.refresh(loan)
    return loan


async def test_get_statement_returns_lines_in_order(loan_with_repayment, tenant_session):
    """Statement lines returned in chronological order."""
    svc = LoanStatementService(tenant_session)
    lines = await svc.get_statement(loan_id=loan_with_repayment.id)

    assert len(lines) >= 2  # at least disbursement + repayment
    # Verify chronological order.
    for i in range(len(lines) - 1):
        assert lines[i].date <= lines[i + 1].date


async def test_get_statement_running_balance_correct(loan_with_repayment, tenant_session):
    """running_balance accumulates correctly across lines."""
    svc = LoanStatementService(tenant_session)
    lines = await svc.get_statement(loan_id=loan_with_repayment.id)

    # First line is the disbursement — running balance should be 120000 (debit opens receivable).
    assert lines[0].running_balance == Decimal("120000")
    # After repayment of 21800, running_balance decreases.
    # Find the repayment line.
    total_debit = sum(l.debit for l in lines)
    total_credit = sum(l.credit for l in lines)
    final_balance = total_debit - total_credit
    assert lines[-1].running_balance == final_balance


async def test_get_statement_date_filter(loan_with_repayment, tenant_session):
    """Date filter restricts lines to the given range."""
    svc = LoanStatementService(tenant_session)
    # Filter to a date range that excludes the disbursement (Jan 2026).
    lines = await svc.get_statement(
        loan_id=loan_with_repayment.id,
        from_date=date(2026, 3, 1),
        to_date=date(2026, 12, 31),
    )
    # No lines expected in March+ for this loan (disbursed Jan, repaid Feb).
    for line in lines:
        assert line.date >= date(2026, 3, 1)
        assert line.date <= date(2026, 12, 31)


async def test_get_statement_empty_range(loan_with_repayment, tenant_session):
    """Date range with no activity returns empty list."""
    svc = LoanStatementService(tenant_session)
    lines = await svc.get_statement(
        loan_id=loan_with_repayment.id,
        from_date=date(2030, 1, 1),
        to_date=date(2030, 12, 31),
    )
    assert lines == []


async def test_get_statement_line_fields(loan_with_repayment, tenant_session):
    """Each StatementLine has required fields."""
    svc = LoanStatementService(tenant_session)
    lines = await svc.get_statement(loan_id=loan_with_repayment.id)

    for line in lines:
        assert isinstance(line.date, date)
        assert isinstance(line.description, str)
        assert isinstance(line.debit, Decimal)
        assert isinstance(line.credit, Decimal)
        assert isinstance(line.running_balance, Decimal)
        assert line.line_type in (
            "disbursement", "repayment", "interest_booked",
            "interest_accrual", "penalty_assessed", "write_off", "recovery", "other"
        )
```

- [ ] **Step 2: Run to confirm failure**

```
pytest tests/modules/credit/test_statement_service.py -v
```

Expected: `FAILED` — `LoanStatementService` not found.

- [ ] **Step 3: Create `app/modules/credit/services/statement.py`**

```python
"""LoanStatementService — JSON statement assembly and WeasyPrint PDF rendering."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import Loan
from app.modules.fees.models import FeeAssessment
from app.modules.ledger.models import JournalEntry, JournalLine

_log = structlog.get_logger(__name__)

_LINE_TYPE_MAP: dict[str, str] = {
    "LOAN-DISB": "disbursement",
    "LOAN-INT": "interest_booked",
    "LOAN-ACC": "interest_accrual",
    "LOAN-REP": "repayment",
    "LOAN-WO": "write_off",
    "LOAN-REC": "recovery",
}


@dataclass
class StatementLine:
    date: date
    line_type: str
    description: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal = field(default=Decimal("0"))


class LoanStatementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_statement(
        self,
        *,
        loan_id: uuid.UUID,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[StatementLine]:
        """Assemble statement lines from journal_lines and fee_assessments.

        Lines are ordered chronologically. running_balance is computed by replay:
        debits increase the receivable (money owed), credits decrease it.

        Args:
            loan_id: UUID of the loan.
            from_date: Optional start of date filter (inclusive).
            to_date: Optional end of date filter (inclusive).

        Returns:
            List of StatementLine in ascending date order.
        """
        # ── 1. Load journal lines for this loan sub-ledger ────────────────────
        jl_query = (
            select(JournalLine, JournalEntry)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(
                JournalLine.sub_ledger_type == "loan",
                JournalLine.sub_ledger_id == loan_id,
            )
            .order_by(JournalEntry.posted_at)
        )
        jl_rows = (await self._session.execute(jl_query)).all()

        # ── 2. Load fee assessments for this loan ─────────────────────────────
        fa_query = (
            select(FeeAssessment)
            .where(
                FeeAssessment.target_type == "loan",
                FeeAssessment.target_id == loan_id,
            )
            .order_by(FeeAssessment.assessed_at)
        )
        fee_rows = (await self._session.scalars(fa_query)).all()

        # ── 3. Build raw lines ────────────────────────────────────────────────
        raw_lines: list[tuple[datetime, StatementLine]] = []

        for jl, je in jl_rows:
            line_type = "other"
            for prefix, lt in _LINE_TYPE_MAP.items():
                if je.reference.startswith(prefix):
                    line_type = lt
                    break

            raw_lines.append(
                (
                    je.posted_at,
                    StatementLine(
                        date=je.posted_at.date(),
                        line_type=line_type,
                        description=je.description,
                        debit=jl.debit_amount,
                        credit=jl.credit_amount,
                    ),
                )
            )

        for fa in fee_rows:
            raw_lines.append(
                (
                    fa.assessed_at,
                    StatementLine(
                        date=fa.assessed_at.date(),
                        line_type="penalty_assessed",
                        description=f"Fee assessed: {fa.amount}",
                        debit=fa.amount,
                        credit=Decimal("0"),
                    ),
                )
            )

        # ── 4. Sort by timestamp ──────────────────────────────────────────────
        raw_lines.sort(key=lambda x: x[0])

        # ── 5. Apply date filter ──────────────────────────────────────────────
        lines = [sl for _, sl in raw_lines]
        if from_date is not None:
            lines = [sl for sl in lines if sl.date >= from_date]
        if to_date is not None:
            lines = [sl for sl in lines if sl.date <= to_date]

        # ── 6. Compute running_balance by replay (from beginning, not filtered start) ──
        # We need to replay from the full history to get a correct opening balance,
        # then annotate only the filtered lines.
        all_lines = [sl for _, sl in raw_lines]
        balance = Decimal("0")
        balance_at: dict[int, Decimal] = {}
        for i, sl in enumerate(all_lines):
            balance = balance + sl.debit - sl.credit
            balance_at[id(sl)] = balance

        for sl in lines:
            sl.running_balance = balance_at[id(sl)]

        return lines

    async def render_pdf(
        self,
        *,
        loan_id: uuid.UUID,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> bytes:
        """Render loan statement as PDF bytes.

        Flow:
            1. Call get_statement() for lines.
            2. Load loan + member details.
            3. Render Jinja2 HTML template.
            4. Convert to PDF via WeasyPrint.
        """
        import jinja2
        import weasyprint
        from pathlib import Path

        lines = await self.get_statement(
            loan_id=loan_id, from_date=from_date, to_date=to_date
        )

        loan = await self._session.get(Loan, loan_id)
        if loan is None:
            raise ValueError(f"Loan '{loan_id}' not found")

        template_dir = Path(__file__).parent.parent / "templates"
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(template_dir)),
            autoescape=True,
        )
        template = env.get_template("loan_statement.html")
        html_str = template.render(
            loan=loan,
            lines=lines,
            from_date=from_date,
            to_date=to_date,
            generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        )

        pdf_bytes: bytes = weasyprint.HTML(string=html_str).write_pdf()
        return pdf_bytes
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/modules/credit/test_statement_service.py -v
```

Expected: All 5 tests **PASS**.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/services/statement.py \
        tests/modules/credit/test_statement_service.py
git commit -m "feat(credit): LoanStatementService — JSON statement assembly with running_balance"
```

---

## Task 3: Jinja2 HTML template

**Files:**
- Create: `app/modules/credit/templates/loan_statement.html`

- [ ] **Step 1: Create the template directory and file**

```bash
mkdir -p app/modules/credit/templates
```

Create `app/modules/credit/templates/loan_statement.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Loan Statement — {{ loan.loan_reference }}</title>
  <style>
    body { font-family: Arial, sans-serif; font-size: 12px; color: #222; margin: 40px; }
    h1 { font-size: 18px; margin-bottom: 4px; }
    h2 { font-size: 14px; color: #555; margin-bottom: 20px; }
    .meta { display: flex; gap: 40px; margin-bottom: 24px; }
    .meta div { line-height: 1.8; }
    .meta strong { display: inline-block; width: 160px; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    thead tr { background: #1a3c6e; color: #fff; }
    thead th { padding: 8px 10px; text-align: left; font-size: 11px; }
    tbody tr:nth-child(even) { background: #f5f5f5; }
    tbody td { padding: 6px 10px; border-bottom: 1px solid #ddd; }
    .amount { text-align: right; }
    .balance { text-align: right; font-weight: bold; }
    tfoot td { padding: 8px 10px; font-size: 11px; color: #777; }
    .footer { margin-top: 32px; font-size: 10px; color: #999; text-align: center; }
  </style>
</head>
<body>
  <h1>Loan Statement</h1>
  <h2>{{ loan.loan_reference }}</h2>

  <div class="meta">
    <div>
      <strong>Loan Reference:</strong> {{ loan.loan_reference }}<br>
      <strong>Member ID:</strong> {{ loan.member_id }}<br>
      <strong>Principal Amount:</strong> {{ "{:,.2f}".format(loan.principal_amount) }}<br>
      <strong>Interest Rate:</strong> {{ loan.annual_interest_rate }}% p.a. ({{ loan.interest_method }})<br>
    </div>
    <div>
      <strong>Status:</strong> {{ loan.status }}<br>
      <strong>Disbursed:</strong> {{ loan.disbursed_at.strftime("%Y-%m-%d") if loan.disbursed_at else "—" }}<br>
      <strong>Maturity Date:</strong> {{ loan.maturity_date or "—" }}<br>
      <strong>Outstanding:</strong> {{ "{:,.2f}".format(loan.outstanding_principal) }}<br>
    </div>
    <div>
      <strong>Statement Period:</strong>
        {% if from_date %}{{ from_date }}{% else %}All{% endif %}
        —
        {% if to_date %}{{ to_date }}{% else %}present{% endif %}<br>
      <strong>Generated:</strong> {{ generated_at }}<br>
    </div>
  </div>

  {% if lines %}
  <table>
    <thead>
      <tr>
        <th>Date</th>
        <th>Type</th>
        <th>Description</th>
        <th class="amount">Debit</th>
        <th class="amount">Credit</th>
        <th class="balance">Balance</th>
      </tr>
    </thead>
    <tbody>
      {% for line in lines %}
      <tr>
        <td>{{ line.date }}</td>
        <td>{{ line.line_type | replace("_", " ") | title }}</td>
        <td>{{ line.description }}</td>
        <td class="amount">{% if line.debit > 0 %}{{ "{:,.2f}".format(line.debit) }}{% endif %}</td>
        <td class="amount">{% if line.credit > 0 %}{{ "{:,.2f}".format(line.credit) }}{% endif %}</td>
        <td class="balance">{{ "{:,.2f}".format(line.running_balance) }}</td>
      </tr>
      {% endfor %}
    </tbody>
    <tfoot>
      <tr>
        <td colspan="6">{{ lines | length }} transaction(s)</td>
      </tr>
    </tfoot>
  </table>
  {% else %}
  <p>No transactions in the selected period.</p>
  {% endif %}

  <div class="footer">
    This statement is computer-generated and does not require a signature.
  </div>
</body>
</html>
```

- [ ] **Step 2: Verify template renders without error**

Run a quick inline test:

```bash
python - <<'EOF'
import asyncio, uuid
from pathlib import Path
import jinja2

template_dir = Path("app/modules/credit/templates")
env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(template_dir)), autoescape=True)
tmpl = env.get_template("loan_statement.html")

class FakeLoan:
    loan_reference = "LN-TEST-001"
    member_id = uuid.uuid4()
    principal_amount = 500000
    annual_interest_rate = 18
    interest_method = "flat"
    status = "disbursed"
    disbursed_at = None
    maturity_date = None
    outstanding_principal = 480000

html = tmpl.render(loan=FakeLoan(), lines=[], from_date=None, to_date=None, generated_at="2026-01-01 00:00 UTC")
print("Template OK — length:", len(html))
EOF
```

Expected: `Template OK — length: <number>` with no errors.

- [ ] **Step 3: Commit**

```bash
git add app/modules/credit/templates/loan_statement.html
git commit -m "feat(credit): Jinja2 HTML template for loan statement PDF"
```

---

## Task 4: PDF rendering test

**Files:**
- Modify: `tests/modules/credit/test_statement_service.py`

- [ ] **Step 1: Add PDF test**

Append to `tests/modules/credit/test_statement_service.py`:

```python
async def test_render_pdf_returns_bytes(loan_with_repayment, tenant_session):
    """render_pdf() returns bytes with PDF magic bytes."""
    svc = LoanStatementService(tenant_session)
    pdf_bytes = await svc.render_pdf(loan_id=loan_with_repayment.id)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    # PDF files start with %PDF
    assert pdf_bytes[:4] == b"%PDF"


async def test_render_pdf_date_filtered(loan_with_repayment, tenant_session):
    """render_pdf() with date range returns valid PDF."""
    svc = LoanStatementService(tenant_session)
    pdf_bytes = await svc.render_pdf(
        loan_id=loan_with_repayment.id,
        from_date=date(2026, 1, 1),
        to_date=date(2026, 12, 31),
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes[:4] == b"%PDF"
```

- [ ] **Step 2: Run tests**

```
pytest tests/modules/credit/test_statement_service.py -v
```

Expected: All 7 tests **PASS** (5 original + 2 PDF tests).

- [ ] **Step 3: Commit**

```bash
git add tests/modules/credit/test_statement_service.py
git commit -m "test(credit): PDF rendering tests for LoanStatementService"
```

---

## Task 5: Statement schemas and API endpoints

**Files:**
- Modify: `app/modules/credit/schemas.py`
- Modify: `app/modules/credit/api.py`

- [ ] **Step 1: Add statement schemas to `schemas.py`**

Open `app/modules/credit/schemas.py` and add:

```python
# ── Loan Statement ────────────────────────────────────────────────────────────


class StatementLineOut(BaseModel):
    date: date
    line_type: str
    description: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal

    model_config = ConfigDict(from_attributes=True)


class LoanStatementOut(BaseModel):
    loan_id: uuid.UUID
    from_date: date | None
    to_date: date | None
    lines: list[StatementLineOut]
```

- [ ] **Step 2: Add endpoints to `api.py`**

Add `StatementLineOut`, `LoanStatementOut` to the schema imports. Then add:

```python
from app.modules.credit.services.statement import LoanStatementService
```

Add the two statement endpoints after the recovery endpoint:

```python
# ── Loan Statements ───────────────────────────────────────────────────────────


@router.get("/loans/{loan_id}/statement", response_model=LoanStatementOut)
async def get_loan_statement(
    loan_id: uuid.UUID,
    session: Session,
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
) -> LoanStatementOut:
    """Return JSON loan statement with running balance."""
    svc = LoanStatementService(session)
    lines = await svc.get_statement(
        loan_id=loan_id, from_date=from_date, to_date=to_date
    )
    return LoanStatementOut(
        loan_id=loan_id,
        from_date=from_date,
        to_date=to_date,
        lines=[
            StatementLineOut(
                date=line.date,
                line_type=line.line_type,
                description=line.description,
                debit=line.debit,
                credit=line.credit,
                running_balance=line.running_balance,
            )
            for line in lines
        ],
    )


@router.get("/loans/{loan_id}/statement.pdf")
async def get_loan_statement_pdf(
    loan_id: uuid.UUID,
    session: Session,
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
) -> Response:
    """Return PDF loan statement."""
    from fastapi.responses import Response as FastAPIResponse

    svc = LoanStatementService(session)
    pdf_bytes = await svc.render_pdf(
        loan_id=loan_id, from_date=from_date, to_date=to_date
    )
    return FastAPIResponse(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="statement-{loan_id}.pdf"'
        },
    )
```

Note: import `Response` at top of file: `from fastapi import APIRouter, Depends, HTTPException, Query, Response`

- [ ] **Step 3: Run import smoke test**

```bash
python -c "from app.main import app; print('OK')"
```

Expected: `OK` with no errors.

- [ ] **Step 4: Run full credit test suite**

```
pytest tests/modules/credit/ -v --tb=short
```

Expected: All tests **PASS**.

- [ ] **Step 5: Commit**

```bash
git add app/modules/credit/schemas.py \
        app/modules/credit/api.py
git commit -m "feat(credit): GET /credit/loans/{id}/statement and statement.pdf endpoints"
```

---

## Verification Checklist

- [ ] `pytest tests/modules/credit/test_statement_service.py -v` — all 7 tests pass
- [ ] Statement lines in chronological order (verified by test)
- [ ] `running_balance` correct after each event (verified by test)
- [ ] Date filter returns only lines in range (verified by test)
- [ ] PDF endpoint returns `bytes` starting with `%PDF` (verified by test)
- [ ] `python -c "from app.main import app"` — no import errors
