# Consolidated Member Statement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A member downloads a consolidated PDF statement (savings + shares + loans + fees) on demand from the member portal, with an optional date range and an in-browser HTML preview.

**Architecture:** A new on-demand (NOT materialized-run) statement in the reporting module: `MemberStatementService.build_context` gathers live data by importing sibling modules' models (the established reporting pattern — see `services/savings_statement.py`), a Jinja2 template renders it, and the existing WeasyPrint `_base.py` pipeline produces the PDF. `GET /member/statement?from_date=&to_date=&format=pdf|html` is gated by `CurrentMember` and is inherently member-scoped (no id params). The portal adds a "Statements" nav item, a date-range page, and a Next.js route-handler proxy (`/api/member/statement`) that carries the member Bearer token — the same pattern as `/api/credit/loans/[id]/statement-pdf`.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Jinja2 + WeasyPrint (backend), pytest/httpx stub-auth (tests), Next.js 15 App Router + `@sacco/ui` (portal), vitest (portal tests).

This is increment 4 (final) of the 2026-06-29 member self-service design
(`docs/superpowers/specs/2026-06-29-member-self-service-design.md`). Increments 1–3 are on `main`.
Branch: `feat/member-statement` (from `main`).

## Global Constraints

- The endpoint is gated by `CurrentMember` + the subscription gate (`get_tenant_session`); it never accepts a member id — everything scopes to `current_member.id`. There is no cross-member path (no id params).
- Statement with no data in range → valid empty-state PDF, **200** (never 404/empty body).
- `format=pdf` (default) streams `application/pdf` as an attachment; `format=html` returns the same rendered content as `text/html` for in-browser preview. No JSON format, no CSV.
- Synchronous rendering via the existing WeasyPrint pipeline (`app/modules/reporting/_base.py`). No async generation, no notifications (Phase 3), no object storage.
- Date range is optional. `from_date > to_date` → **422**. The range filters transaction-level rows (savings transactions, share transactions) and fee assessments (`assessed_at` date); loans always show current snapshot state + full active schedule (`is_superseded = false`).
- Money formatting in the template: `"{:,.4f}".format(...)` and per-account running balances computed with the savings credit-type convention `{'deposit', 'SYSTEM_CREDIT', 'EXTERNAL_CREDIT'}` add / everything else subtracts (same as `SavingsStatementService`).
- Reporting module MAY import sibling modules' models (established pattern in `app/modules/reporting/services/`). Do not add new cross-module service interfaces for this.
- Member nav becomes Dashboard / Savings / Shares / Loans / Fees / **Statements** / Profile.
- The portal proxies the download through a Next.js route handler (access token is server-side; a raw `<a>` to FastAPI cannot carry it). Statement page is a small RHF+Zod form (contract J) with `DateInput`s; buttons open the proxy URL.
- ruff + mypy (strict) clean; all DB access async.

## Prerequisites

Branch `feat/member-statement` checked out (created from `main`). Docker Postgres test DB healthy. WeasyPrint importable in the venv (existing reporting tests already exercise it).

## File Structure

```
app/modules/reporting/_base.py                       (modify: +render_html; render_pdf uses it)
app/modules/reporting/services/member_statement.py   (create: MemberStatementService)
app/modules/reporting/templates/member_statement.html (create)
app/modules/reporting/api.py                         (modify: +member_router /member/statement)
app/main.py                                          (modify: register reporting member_router)
tests/modules/reporting/test_base.py                 (modify: +render_html test)
tests/modules/reporting/test_member_statement.py     (create: service + API tests)

admin/apps/portal/app/api/member/statement/route.ts  (create: PDF/HTML proxy)
admin/apps/portal/app/member/(authed)/statements/page.tsx (create)
admin/apps/portal/app/member/(authed)/statements/_components/StatementForm.tsx (create)
admin/apps/portal/app/member/(authed)/statements/__tests__/StatementForm.test.tsx (create)
admin/packages/schemas/src/member.ts                 (modify: +memberStatementRangeSchema)
admin/packages/schemas/src/__tests__/member.test.ts  (modify: +range schema tests)
admin/apps/portal/src/components/shell/nav-config.tsx (modify: +Statements member nav item)

CLAUDE.md                                            (modify: member statement contract, Task 5)
```

---

### Task 1: `render_html` in `_base.py`

**Files:**
- Modify: `app/modules/reporting/_base.py`
- Test: `tests/modules/reporting/test_base.py` (append)

**Interfaces:**
- Consumes: existing `_TEMPLATE_DIR`, Jinja2.
- Produces: `render_html(template_name: str, context: dict[str, Any]) -> str` — the rendered HTML string. `render_pdf` keeps its exact signature (`(template_name, context) -> bytes`) but delegates to `render_html` internally (consumed by Tasks 2–3).

- [ ] **Step 1: Write the failing test**

Append to `tests/modules/reporting/test_base.py`:

```python
def test_render_html_returns_rendered_string() -> None:
    from app.modules.reporting._base import render_html

    html = render_html(
        "trial_balance.html",
        {
            "as_of_date": date(2026, 1, 31),
            "generated_at": datetime(2026, 1, 31, 12, 0, tzinfo=UTC),
            "rows": [],
            "total_debits": Decimal("0"),
            "total_credits": Decimal("0"),
        },
    )
    assert isinstance(html, str)
    assert "<html" in html
```

(If `date` / `datetime` / `UTC` / `Decimal` are not already imported in this test file, add them to its imports.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/modules/reporting/test_base.py -q`
Expected: FAIL — `ImportError: cannot import name 'render_html'`.

- [ ] **Step 3: Write the implementation**

In `app/modules/reporting/_base.py`, replace the body of `render_pdf` and add `render_html` above it:

```python
def render_html(template_name: str, context: dict[str, Any]) -> str:
    """Render a Jinja2 HTML template to a string.

    Used directly for format=html previews and by render_pdf.
    """
    import jinja2  # noqa: PLC0415 — optional dep, imported lazily

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template(template_name)
    return template.render(**context)


def render_pdf(template_name: str, context: dict[str, Any]) -> bytes:
    """Render a Jinja2 HTML template to PDF bytes via WeasyPrint."""
    import weasyprint  # noqa: PLC0415 — optional dep, imported lazily

    pdf_bytes: bytes = weasyprint.HTML(string=render_html(template_name, context)).write_pdf()
    return pdf_bytes
```

Keep the module docstring and `render_csv` untouched; update the docstring's summary lines to mention `render_html`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/modules/reporting/test_base.py -q`
Expected: PASS (all, including the pre-existing render_pdf/render_csv tests).

- [ ] **Step 5: Lint, typecheck, commit**

Run: `python -m ruff check app/ tests/ && python -m mypy app/`
Expected: clean.

```bash
git add app/modules/reporting/_base.py tests/modules/reporting/test_base.py
git commit -m "refactor(reporting): extract render_html from render_pdf"
```

---

### Task 2: `MemberStatementService` + `member_statement.html`

**Files:**
- Create: `app/modules/reporting/services/member_statement.py`
- Create: `app/modules/reporting/templates/member_statement.html`
- Test: `tests/modules/reporting/test_member_statement.py` (create — service section)

**Interfaces:**
- Consumes: `Member` (members), `SavingsAccount`/`SavingsTransaction` (savings), `MemberShareAccount`/`ShareTransaction`/`ShareProduct` (shares), `Loan`/`LoanInstallment` (credit), `FeeAssessment`/`FeeType` (fees), `render_pdf`/`render_html` (Task 1).
- Produces (consumed by Task 3):
  - `MemberStatementService(session).build_context(member: Member, *, from_date: date | None, to_date: date | None) -> dict[str, Any]` with keys:
    `member` (the row), `from_date`, `to_date`, `generated_at: datetime`,
    `savings: list[dict]` (`account`, `opening_balance: Decimal`, `closing_balance: Decimal`, `lines: list[dict]` each `{txn, signed: Decimal, running: Decimal}`),
    `shares: list[dict]` (`account`, `product_name: str`, `total_quantity: int`, `total_value: Decimal`, `txns: list[ShareTransaction]`),
    `loans: list[dict]` (`loan`, `installments: list[LoanInstallment]`),
    `fees: list[dict]` (`assessment`, `fee_name: str`).
  - Template `member_statement.html` rendering that context (sections: Savings / Shares / Loans / Fees, each with an empty-state line).

- [ ] **Step 1: Write the failing tests**

Create `tests/modules/reporting/test_member_statement.py` (session/seed pattern copied from `tests/modules/reporting/test_savings_statement.py`):

```python
# tests/modules/reporting/test_member_statement.py
"""Consolidated member statement: service context + HTTP endpoint."""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from app.modules.credit.models import Loan, LoanApplication, LoanInstallment, LoanProduct
from app.modules.fees.models import FeeAssessment, FeeType
from app.modules.ledger.models import JournalEntry
from app.modules.members.models import Member
from app.modules.savings.models import SavingsAccount, SavingsProduct, SavingsTransaction
from app.modules.shares.models import MemberShareAccount, ShareProduct, ShareTransaction

TEST_SCHEMA = "tenant_test"
_SYSTEM = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _new_session(engine: AsyncEngine) -> AsyncSession:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()

    @event.listens_for(session.sync_session, "after_begin")
    def _set_path(sess, tx, conn):  # noqa: ANN001, ANN202
        conn.exec_driver_sql(f"SET LOCAL search_path TO {TEST_SCHEMA}, platform")

    return session


async def _je(session: AsyncSession, ref: str, when: datetime) -> JournalEntry:
    je = JournalEntry(
        reference=ref,
        description=ref,
        posted_by=str(_SYSTEM),
        posted_at=when,
        idempotency_key=f"mstmt-je-{uuid.uuid4()}",
    )
    session.add(je)
    await session.flush()
    return je


async def _seed_member_with_everything(session: AsyncSession) -> uuid.UUID:
    """One member with: 1 savings account (3 txns), 1 share account (1 txn),
    1 disbursed loan (2 installments), 1 fee assessment. Txn dates span
    2026-01-10 .. 2026-02-15 so range tests can slice."""
    member = Member(
        member_number=f"M-{uuid.uuid4().hex[:8]}",
        full_name="Statement Member",
        date_of_birth=date(1990, 1, 1),
        gender="female",
        status="active",
        portal_enabled=True,
    )
    session.add(member)
    await session.flush()

    # Savings: deposits 1000 (Jan 10), 500 (Jan 20); withdrawal 200 (Feb 15).
    sav_product = SavingsProduct(
        name="Regular Savings",
        interest_rate=Decimal("5.00"),
        minimum_balance=Decimal("0"),
        liability_account_id=uuid.uuid4(),
        is_active=True,
    )
    session.add(sav_product)
    await session.flush()
    account = SavingsAccount(
        member_id=member.id,
        savings_product_id=sav_product.id,
        product_name="Regular Savings",
        interest_rate=Decimal("5.00"),
        minimum_balance=Decimal("0"),
        liability_account_id=sav_product.liability_account_id,
    )
    session.add(account)
    await session.flush()
    for when, txn_type, amount in (
        (datetime(2026, 1, 10, tzinfo=UTC), "deposit", Decimal("1000")),
        (datetime(2026, 1, 20, tzinfo=UTC), "deposit", Decimal("500")),
        (datetime(2026, 2, 15, tzinfo=UTC), "withdrawal", Decimal("200")),
    ):
        je = await _je(session, f"MSTMT-SAV-{uuid.uuid4().hex[:6]}", when)
        session.add(
            SavingsTransaction(
                savings_account_id=account.id,
                transaction_type=txn_type,
                amount=amount,
                narration=f"{txn_type} {amount}",
                journal_entry_id=je.id,
                posted_by=_SYSTEM,
                posted_at=when,
                idempotency_key=f"mstmt-sav-{uuid.uuid4()}",
            )
        )

    # Shares: one purchase of 10 @ 5000 total (Jan 15).
    share_product = ShareProduct(
        name="Ordinary Shares",
        par_value=Decimal("500"),
        share_capital_account_id=uuid.uuid4(),
        is_active=True,
    )
    session.add(share_product)
    await session.flush()
    share_account = MemberShareAccount(member_id=member.id, share_product_id=share_product.id)
    session.add(share_account)
    await session.flush()
    je = await _je(session, "MSTMT-SHR-1", datetime(2026, 1, 15, tzinfo=UTC))
    session.add(
        ShareTransaction(
            share_account_id=share_account.id,
            transaction_type="purchase",
            quantity=10,
            amount=Decimal("5000"),
            journal_entry_id=je.id,
            posted_by=_SYSTEM,
            posted_at=datetime(2026, 1, 15, tzinfo=UTC),
            idempotency_key=f"mstmt-shr-{uuid.uuid4()}",
        )
    )

    # Loan: active, 2 installments.
    loan_product = LoanProduct(
        name="Statement Loan",
        interest_method="flat",
        annual_interest_rate=Decimal("12.00"),
        repayment_frequency="monthly",
        max_term_periods=24,
        min_amount=Decimal("100"),
        max_amount=Decimal("100000"),
        disbursement_destinations=["cash"],
        gl_principal_receivable_code="1300",
        gl_interest_receivable_code="1310",
        gl_interest_income_code="4100",
    )
    session.add(loan_product)
    await session.flush()
    application = LoanApplication(
        loan_product_id=loan_product.id,
        member_id=member.id,
        requested_amount=Decimal("10000"),
        requested_term_periods=2,
        disbursement_destination="cash",
        status="approved",
        idempotency_key=f"mstmt-app-{uuid.uuid4()}",
    )
    session.add(application)
    await session.flush()
    loan = Loan(
        loan_reference=f"LN-{uuid.uuid4().hex[:8]}",
        loan_application_id=application.id,
        loan_product_id=loan_product.id,
        member_id=member.id,
        status="active",
        principal_amount=Decimal("10000"),
        interest_method="flat",
        annual_interest_rate=Decimal("12.00"),
        repayment_frequency="monthly",
        term_periods=2,
        repayment_allocation="INTEREST_PRINCIPAL",
        disbursement_destination="cash",
        gl_principal_receivable_id=uuid.uuid4(),
        gl_interest_receivable_id=uuid.uuid4(),
        gl_interest_income_id=uuid.uuid4(),
        gl_disbursement_account_id=uuid.uuid4(),
        outstanding_principal=Decimal("10000"),
        disbursed_at=datetime(2026, 1, 5, tzinfo=UTC),
        disbursed_by=_SYSTEM,
        idempotency_key=f"mstmt-loan-{uuid.uuid4()}",
    )
    session.add(loan)
    await session.flush()
    for n in (1, 2):
        session.add(
            LoanInstallment(
                loan_id=loan.id,
                period_number=n,
                due_date=date(2026, 1 + n, 5),
                principal_due=Decimal("5000"),
                interest_due=Decimal("100"),
                total_due=Decimal("5100"),
            )
        )

    # Fee: one member fee assessed Jan 12.
    fee_type = FeeType(
        code=f"MSTMT-{uuid.uuid4().hex[:6]}",
        name="Annual Membership Fee",
        applicable_to="member",
        amount=Decimal("250"),
        currency="UGX",
        trigger_kind="schedule",
        gl_income_account_code="4200",
        gl_receivable_account_code="1200",
    )
    session.add(fee_type)
    await session.flush()
    fee_je = await _je(session, "MSTMT-FEE-1", datetime(2026, 1, 12, tzinfo=UTC))
    session.add(
        FeeAssessment(
            fee_type_id=fee_type.id,
            target_type="member",
            target_id=member.id,
            period_start=date(2026, 1, 1),
            amount=Decimal("250"),
            currency="UGX",
            journal_entry_id=fee_je.id,
            assessed_at=datetime(2026, 1, 12, tzinfo=UTC),
        )
    )
    await session.commit()
    return member.id


async def _cleanup(engine: AsyncEngine) -> None:
    session = _new_session(engine)
    async with session:
        for tbl in (
            "loan_installments",
            "loans",
            "loan_applications",
            "loan_products",
            "fee_assessments",
            "fee_types",
            "share_transactions",
            "member_share_accounts",
            "share_products",
            "savings_transactions",
            "savings_accounts",
            "savings_products",
        ):
            await session.execute(text(f"DELETE FROM {tbl}"))  # noqa: S608
        await session.execute(text("DELETE FROM journal_entries WHERE reference LIKE 'MSTMT-%'"))
        await session.execute(
            text("DELETE FROM audit_log WHERE table_name IN ('members', 'loan_products', 'loan_applications', 'loans', 'share_products', 'member_share_accounts', 'fee_types', 'savings_products', 'savings_accounts')")
        )
        await session.execute(text("DELETE FROM members"))
        await session.commit()


@pytest.fixture(autouse=True)
async def _clean(test_engine: AsyncEngine):  # noqa: ANN201
    yield
    await _cleanup(test_engine)


# ── Service ───────────────────────────────────────────────────────────────────


async def test_build_context_gathers_all_sections(test_engine: AsyncEngine) -> None:
    from app.modules.reporting.services.member_statement import MemberStatementService

    member_id = await _seed_member_with_everything(_s := _new_session(test_engine))
    await _s.close()
    session = _new_session(test_engine)
    async with session:
        member = (
            await session.execute(text("SELECT 1"))  # warm the search_path listener
        ) and (await session.get(Member, member_id))
        assert member is not None
        ctx = await MemberStatementService(session).build_context(
            member, from_date=None, to_date=None
        )
    assert ctx["member"].id == member_id
    sav = ctx["savings"][0]
    assert sav["opening_balance"] == Decimal("0")
    assert sav["closing_balance"] == Decimal("1300")  # 1000 + 500 - 200
    assert [ln["running"] for ln in sav["lines"]] == [
        Decimal("1000"),
        Decimal("1500"),
        Decimal("1300"),
    ]
    shares = ctx["shares"][0]
    assert shares["total_quantity"] == 10
    assert shares["total_value"] == Decimal("5000")
    assert shares["product_name"] == "Ordinary Shares"
    loan = ctx["loans"][0]
    assert loan["loan"].outstanding_principal == Decimal("10000")
    assert [i.period_number for i in loan["installments"]] == [1, 2]
    assert ctx["fees"][0]["fee_name"] == "Annual Membership Fee"


async def test_build_context_range_filters_and_opening_balance(
    test_engine: AsyncEngine,
) -> None:
    from app.modules.reporting.services.member_statement import MemberStatementService

    member_id = await _seed_member_with_everything(_s := _new_session(test_engine))
    await _s.close()
    session = _new_session(test_engine)
    async with session:
        member = await session.get(Member, member_id)
        assert member is not None
        ctx = await MemberStatementService(session).build_context(
            member, from_date=date(2026, 2, 1), to_date=date(2026, 2, 28)
        )
    sav = ctx["savings"][0]
    # Jan deposits fall before the range -> opening balance, not lines.
    assert sav["opening_balance"] == Decimal("1500")
    assert len(sav["lines"]) == 1
    assert sav["lines"][0]["running"] == Decimal("1300")
    # Share purchase (Jan 15) is outside the range.
    assert ctx["shares"][0]["txns"] == []
    # Fee assessed Jan 12 is outside the range.
    assert ctx["fees"] == []
    # Loans always show (current snapshot + schedule).
    assert len(ctx["loans"]) == 1


async def test_member_statement_template_renders_pdf(test_engine: AsyncEngine) -> None:
    from app.modules.reporting._base import render_pdf
    from app.modules.reporting.services.member_statement import MemberStatementService

    member_id = await _seed_member_with_everything(_s := _new_session(test_engine))
    await _s.close()
    session = _new_session(test_engine)
    async with session:
        member = await session.get(Member, member_id)
        assert member is not None
        ctx = await MemberStatementService(session).build_context(
            member, from_date=None, to_date=None
        )
    pdf = render_pdf("member_statement.html", ctx)
    assert pdf[:4] == b"%PDF"
```

Note: model fields verified against the code 2026-07-10: `ShareProduct(par_value,
share_capital_account_id)`, `LoanInstallment.is_superseded` exists,
`FeeAssessment.journal_entry_id` is a NOT NULL FK (hence the seeded JE).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/modules/reporting/test_member_statement.py -q`
Expected: FAIL — `ModuleNotFoundError: app.modules.reporting.services.member_statement`.
(If the seed itself errors on a column name, fix the seed against the real models first.)

- [ ] **Step 3: Write the implementation**

Create `app/modules/reporting/services/member_statement.py`:

```python
# app/modules/reporting/services/member_statement.py
"""MemberStatementService — on-demand consolidated member statement.

Unlike the other reporting services this does NOT materialize report runs:
the statement is rendered live at request time, scoped to one member.
Reporting is the sanctioned cross-module read surface, so importing sibling
modules' models here follows the established pattern.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.members.models import Member

from app.modules.credit.models import Loan, LoanInstallment
from app.modules.fees.models import FeeAssessment, FeeType
from app.modules.savings.models import SavingsAccount, SavingsTransaction
from app.modules.shares.models import MemberShareAccount, ShareProduct, ShareTransaction

# Same signing convention as SavingsStatementService.
_CREDIT_TYPES = frozenset({"deposit", "SYSTEM_CREDIT", "EXTERNAL_CREDIT"})


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)


def _day_end_exclusive(d: date) -> datetime:
    return _day_start(d) + timedelta(days=1)


class MemberStatementService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def build_context(
        self, member: Member, *, from_date: date | None, to_date: date | None
    ) -> dict[str, Any]:
        """Gather savings/shares/loans/fees for one member into a template context.

        The range filters transaction-level rows; loans always show current
        snapshot state + the active schedule. Savings opening balance is the
        signed sum of transactions before from_date.
        """
        return {
            "member": member,
            "from_date": from_date,
            "to_date": to_date,
            "generated_at": datetime.now(tz=UTC),
            "savings": await self._savings(member.id, from_date, to_date),
            "shares": await self._shares(member.id, from_date, to_date),
            "loans": await self._loans(member.id),
            "fees": await self._fees(member.id, from_date, to_date),
        }

    @staticmethod
    def _signed(txn_type: str, amount: Decimal) -> Decimal:
        return amount if txn_type in _CREDIT_TYPES else -amount

    async def _savings(
        self, member_id: Any, from_date: date | None, to_date: date | None
    ) -> list[dict[str, Any]]:
        accounts = list(
            (
                await self._session.execute(
                    select(SavingsAccount)
                    .where(SavingsAccount.member_id == member_id)
                    .order_by(SavingsAccount.created_at)
                )
            ).scalars()
        )
        out: list[dict[str, Any]] = []
        for account in accounts:
            txns = list(
                (
                    await self._session.execute(
                        select(SavingsTransaction)
                        .where(SavingsTransaction.savings_account_id == account.id)
                        .order_by(SavingsTransaction.posted_at)
                    )
                ).scalars()
            )
            opening = Decimal("0")
            lines: list[dict[str, Any]] = []
            running = Decimal("0")
            for txn in txns:
                signed = self._signed(txn.transaction_type, txn.amount)
                if from_date is not None and txn.posted_at < _day_start(from_date):
                    opening += signed
                    running += signed
                    continue
                if to_date is not None and txn.posted_at >= _day_end_exclusive(to_date):
                    continue
                running += signed
                lines.append({"txn": txn, "signed": signed, "running": running})
            closing = lines[-1]["running"] if lines else opening
            out.append(
                {
                    "account": account,
                    "opening_balance": opening,
                    "closing_balance": closing,
                    "lines": lines,
                }
            )
        return out

    async def _shares(
        self, member_id: Any, from_date: date | None, to_date: date | None
    ) -> list[dict[str, Any]]:
        rows = list(
            (
                await self._session.execute(
                    select(MemberShareAccount, ShareProduct)
                    .join(ShareProduct, MemberShareAccount.share_product_id == ShareProduct.id)
                    .where(MemberShareAccount.member_id == member_id)
                    .order_by(MemberShareAccount.created_at)
                )
            ).all()
        )
        out: list[dict[str, Any]] = []
        for account, product in rows:
            txns = list(
                (
                    await self._session.execute(
                        select(ShareTransaction)
                        .where(ShareTransaction.share_account_id == account.id)
                        .order_by(ShareTransaction.posted_at)
                    )
                ).scalars()
            )
            total_quantity = 0
            total_value = Decimal("0")
            in_range: list[ShareTransaction] = []
            for txn in txns:
                sign = 1 if txn.transaction_type == "purchase" else -1
                total_quantity += sign * txn.quantity
                total_value += sign * txn.amount
                if from_date is not None and txn.posted_at < _day_start(from_date):
                    continue
                if to_date is not None and txn.posted_at >= _day_end_exclusive(to_date):
                    continue
                in_range.append(txn)
            out.append(
                {
                    "account": account,
                    "product_name": product.name,
                    "total_quantity": total_quantity,
                    "total_value": total_value,
                    "txns": in_range,
                }
            )
        return out

    async def _loans(self, member_id: Any) -> list[dict[str, Any]]:
        loans = list(
            (
                await self._session.execute(
                    select(Loan).where(Loan.member_id == member_id).order_by(Loan.created_at)
                )
            ).scalars()
        )
        out: list[dict[str, Any]] = []
        for loan in loans:
            installments = list(
                (
                    await self._session.execute(
                        select(LoanInstallment)
                        .where(
                            LoanInstallment.loan_id == loan.id,
                            LoanInstallment.is_superseded.is_(False),
                        )
                        .order_by(LoanInstallment.period_number)
                    )
                ).scalars()
            )
            out.append({"loan": loan, "installments": installments})
        return out

    async def _fees(
        self, member_id: Any, from_date: date | None, to_date: date | None
    ) -> list[dict[str, Any]]:
        q = (
            select(FeeAssessment, FeeType)
            .join(FeeType, FeeAssessment.fee_type_id == FeeType.id)
            .where(
                FeeAssessment.target_type == "member",
                FeeAssessment.target_id == member_id,
            )
            .order_by(FeeAssessment.assessed_at)
        )
        if from_date is not None:
            q = q.where(FeeAssessment.assessed_at >= _day_start(from_date))
        if to_date is not None:
            q = q.where(FeeAssessment.assessed_at < _day_end_exclusive(to_date))
        rows = (await self._session.execute(q)).all()
        return [{"assessment": a, "fee_name": ft.name} for a, ft in rows]
```

Note: `LoanInstallment.is_superseded` — confirm the column name in
`app/modules/credit/models.py` (the v1b contract says installments are marked
`is_superseded=true` on restructuring). If the column is named differently,
match the model.

Create `app/modules/reporting/templates/member_statement.html` (style conventions copied from the sibling templates):

```html
<!-- app/modules/reporting/templates/member_statement.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Member Statement — {{ member.member_number }}</title>
  <style>
    body { font-family: Arial, sans-serif; font-size: 11px; margin: 20px; }
    h1 { font-size: 16px; margin-bottom: 4px; }
    h2 { font-size: 13px; margin: 18px 0 6px; border-bottom: 1px solid #1a5276; padding-bottom: 2px; }
    h3 { font-size: 11px; margin: 10px 0 4px; }
    .meta { color: #555; font-size: 10px; margin-bottom: 16px; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
    th { background: #1a5276; color: white; padding: 5px 8px; text-align: left; }
    td { padding: 4px 8px; border-bottom: 1px solid #e0e0e0; }
    tr:nth-child(even) td { background: #f8f8f8; }
    .num { text-align: right; }
    .cr { color: #1e8449; }
    .dr { color: #c0392b; }
    .empty { color: #888; font-style: italic; margin: 4px 0 10px; }
  </style>
</head>
<body>
  <h1>Member Statement</h1>
  <div class="meta">
    {{ member.full_name }} ({{ member.member_number }}) &nbsp;|&nbsp;
    Period: {{ from_date or 'beginning' }} to {{ to_date or 'today' }} &nbsp;|&nbsp;
    Generated: {{ generated_at.strftime('%Y-%m-%d %H:%M UTC') }}
  </div>

  <h2>Savings</h2>
  {% if not savings %}<p class="empty">No savings accounts.</p>{% endif %}
  {% for s in savings %}
  <h3>{{ s.account.product_name }} — opening {{ "{:,.4f}".format(s.opening_balance) }},
      closing {{ "{:,.4f}".format(s.closing_balance) }}</h3>
  {% if not s.lines %}<p class="empty">No transactions in this period.</p>{% else %}
  <table>
    <thead><tr><th>Date</th><th>Type</th><th>Narration</th><th class="num">Amount</th><th class="num">Balance</th></tr></thead>
    <tbody>
      {% for ln in s.lines %}
      <tr>
        <td>{{ ln.txn.posted_at.strftime('%Y-%m-%d') }}</td>
        <td>{{ ln.txn.transaction_type }}</td>
        <td>{{ ln.txn.narration or '—' }}</td>
        <td class="num {% if ln.signed >= 0 %}cr{% else %}dr{% endif %}">{{ "{:,.4f}".format(ln.txn.amount) }}</td>
        <td class="num">{{ "{:,.4f}".format(ln.running) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
  {% endfor %}

  <h2>Shares</h2>
  {% if not shares %}<p class="empty">No share accounts.</p>{% endif %}
  {% for sh in shares %}
  <h3>{{ sh.product_name }} — {{ sh.total_quantity }} shares, value {{ "{:,.4f}".format(sh.total_value) }}</h3>
  {% if not sh.txns %}<p class="empty">No share transactions in this period.</p>{% else %}
  <table>
    <thead><tr><th>Date</th><th>Type</th><th class="num">Quantity</th><th class="num">Amount</th></tr></thead>
    <tbody>
      {% for txn in sh.txns %}
      <tr>
        <td>{{ txn.posted_at.strftime('%Y-%m-%d') }}</td>
        <td>{{ txn.transaction_type }}</td>
        <td class="num">{{ txn.quantity }}</td>
        <td class="num">{{ "{:,.4f}".format(txn.amount) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
  {% endfor %}

  <h2>Loans</h2>
  {% if not loans %}<p class="empty">No loans.</p>{% endif %}
  {% for l in loans %}
  <h3>{{ l.loan.loan_reference }} — {{ l.loan.status }},
      principal {{ "{:,.4f}".format(l.loan.principal_amount) }},
      outstanding {{ "{:,.4f}".format(l.loan.outstanding_principal) }}</h3>
  {% if not l.installments %}<p class="empty">No schedule.</p>{% else %}
  <table>
    <thead><tr><th>#</th><th>Due Date</th><th class="num">Principal</th><th class="num">Interest</th><th class="num">Total Due</th><th>Status</th></tr></thead>
    <tbody>
      {% for i in l.installments %}
      <tr>
        <td>{{ i.period_number }}</td>
        <td>{{ i.due_date }}</td>
        <td class="num">{{ "{:,.4f}".format(i.principal_due) }}</td>
        <td class="num">{{ "{:,.4f}".format(i.interest_due) }}</td>
        <td class="num">{{ "{:,.4f}".format(i.total_due) }}</td>
        <td>{{ i.status }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
  {% endfor %}

  <h2>Fees</h2>
  {% if not fees %}<p class="empty">No fee assessments in this period.</p>{% else %}
  <table>
    <thead><tr><th>Assessed</th><th>Fee</th><th class="num">Amount</th><th>Status</th></tr></thead>
    <tbody>
      {% for f in fees %}
      <tr>
        <td>{{ f.assessment.assessed_at.strftime('%Y-%m-%d') }}</td>
        <td>{{ f.fee_name }}</td>
        <td class="num">{{ "{:,.4f}".format(f.assessment.amount) }}</td>
        <td>{{ f.assessment.status }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
</body>
</html>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/modules/reporting/test_member_statement.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint, typecheck, commit**

Run: `python -m ruff check app/ tests/ && python -m mypy app/`
Expected: clean.

```bash
git add app/modules/reporting/services/member_statement.py app/modules/reporting/templates/member_statement.html tests/modules/reporting/test_member_statement.py
git commit -m "feat(reporting): consolidated member statement service + template"
```

---

### Task 3: `GET /member/statement` endpoint

**Files:**
- Modify: `app/modules/reporting/api.py`
- Modify: `app/main.py`
- Test: `tests/modules/reporting/test_member_statement.py` (append)

**Interfaces:**
- Consumes: Task 2's `MemberStatementService` + template; Task 1's `render_html`/`render_pdf`; `CurrentMember` from `app.modules.iam.dependencies`.
- Produces: `GET /member/statement?from_date=&to_date=&format=pdf|html` → `application/pdf` attachment (default) or `text/html`. `from_date > to_date` → 422. Router `member_router` exported from `app/modules/reporting/api.py`, registered in `app/main.py`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/reporting/test_member_statement.py`:

```python
# ── HTTP endpoint ─────────────────────────────────────────────────────────────

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.db import get_tenant_session  # noqa: E402
from app.main import app, lifespan  # noqa: E402

HEADERS = {"X-Tenant-Slug": "test-tenant"}


@pytest.fixture
async def client(test_engine: AsyncEngine, tenant_actor_id: uuid.UUID):  # noqa: ANN201
    factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(text(f"SET LOCAL search_path TO {TEST_SCHEMA}, platform"))
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_tenant_session] = _override
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.headers["X-Tenant-Slug"] = "test-tenant"
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)


def _member_headers(member_id: uuid.UUID) -> dict[str, str]:
    return {**HEADERS, "X-Member-Actor-ID": str(member_id)}


async def test_statement_pdf_default(client: AsyncClient, test_engine: AsyncEngine) -> None:
    member_id = await _seed_member_with_everything(_s := _new_session(test_engine))
    await _s.close()
    resp = await client.get("/member/statement", headers=_member_headers(member_id))
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content[:4] == b"%PDF"


async def test_statement_html_preview_contains_sections(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member_id = await _seed_member_with_everything(_s := _new_session(test_engine))
    await _s.close()
    resp = await client.get(
        "/member/statement", params={"format": "html"}, headers=_member_headers(member_id)
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/html")
    html = resp.text
    assert "Savings" in html
    assert "Ordinary Shares" in html
    assert "Annual Membership Fee" in html
    assert "1,300.0000" in html  # savings closing balance


async def test_statement_range_filters_html(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member_id = await _seed_member_with_everything(_s := _new_session(test_engine))
    await _s.close()
    resp = await client.get(
        "/member/statement",
        params={"format": "html", "from_date": "2026-02-01", "to_date": "2026-02-28"},
        headers=_member_headers(member_id),
    )
    assert resp.status_code == 200
    html = resp.text
    assert "No share transactions in this period." in html
    assert "No fee assessments in this period." in html
    assert "withdrawal" in html  # the Feb 15 txn is in range


async def test_statement_empty_member_returns_valid_pdf(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    session = _new_session(test_engine)
    async with session:
        member = Member(
            member_number=f"M-{uuid.uuid4().hex[:8]}",
            full_name="Empty Member",
            date_of_birth=date(1995, 6, 1),
            gender="male",
            status="active",
            portal_enabled=True,
        )
        session.add(member)
        await session.commit()
        member_id = member.id
    resp = await client.get("/member/statement", headers=_member_headers(member_id))
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


async def test_statement_invalid_range_422(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member_id = await _seed_member_with_everything(_s := _new_session(test_engine))
    await _s.close()
    resp = await client.get(
        "/member/statement",
        params={"from_date": "2026-03-01", "to_date": "2026-01-01"},
        headers=_member_headers(member_id),
    )
    assert resp.status_code == 422


async def test_statement_requires_member_auth(client: AsyncClient) -> None:
    # Missing X-Member-Actor-ID (stub mode) -> FastAPI validation 422.
    resp = await client.get("/member/statement", headers=HEADERS)
    assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/modules/reporting/test_member_statement.py -q`
Expected: the 6 new tests FAIL with 404 (route missing); the 3 service tests still pass.

- [ ] **Step 3: Write the implementation**

In `app/modules/reporting/api.py`:

Add to the imports: `CurrentMember` (extend the existing `from app.modules.iam.dependencies import ...` line) and, near the other router declarations:

```python
# Member self-service consolidated statement (on-demand, scoped to the member).
member_router = APIRouter(prefix="/member/statement", tags=["member-reports"])
```

Add the handler (at the end of the file):

```python
@member_router.get("", response_model=None)
async def member_statement(
    session: Session,
    member: CurrentMember,
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    format: str = Query(default="pdf", pattern="^(pdf|html)$"),
) -> Response:
    """Consolidated statement (savings + shares + loans + fees) for the
    current member. Always scoped to the authenticated member — no id
    params, hence no cross-member surface. Empty data renders a valid
    empty-state document (200)."""
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(status_code=422, detail="from_date must be on or before to_date")
    from app.modules.reporting.services.member_statement import (  # noqa: PLC0415
        MemberStatementService,
    )

    context = await MemberStatementService(session).build_context(
        member, from_date=from_date, to_date=to_date
    )
    if format == "html":
        from app.modules.reporting._base import render_html  # noqa: PLC0415

        return Response(
            content=render_html("member_statement.html", context),
            media_type="text/html",
        )
    from app.modules.reporting._base import render_pdf  # noqa: PLC0415

    pdf = render_pdf("member_statement.html", context)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="statement-{member.member_number}.pdf"'
            ),
        },
    )
```

(Check the file's existing imports: `Query`, `Response`, `HTTPException`, `date`, and the `Session` alias already exist for the sibling endpoints; add whatever is missing.)

In `app/main.py`:

```python
from app.modules.reporting.api import member_router as reporting_member_router
```

and register directly after `app.include_router(reporting_router)`:

```python
app.include_router(reporting_member_router)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/modules/reporting/ -q`
Expected: all green (9 tests in the new file; no regressions).

- [ ] **Step 5: Lint, typecheck, commit**

Run: `python -m ruff check app/ tests/ && python -m mypy app/`
Expected: clean.

```bash
git add app/modules/reporting/api.py app/main.py tests/modules/reporting/test_member_statement.py
git commit -m "feat(reporting): GET /member/statement — consolidated PDF/HTML statement"
```

---

### Task 4: Member portal — Statements page + proxy route + nav

**Files:**
- Create: `admin/apps/portal/app/api/member/statement/route.ts`
- Create: `admin/apps/portal/app/member/(authed)/statements/page.tsx`
- Create: `admin/apps/portal/app/member/(authed)/statements/_components/StatementForm.tsx`
- Modify: `admin/packages/schemas/src/member.ts` (+ its test file)
- Modify: `admin/apps/portal/src/components/shell/nav-config.tsx`
- Test: `admin/apps/portal/app/member/(authed)/statements/__tests__/StatementForm.test.tsx` (create)

**Interfaces:**
- Consumes: Task 3's endpoint; `getServerAccessToken("member")` + `getServerTenantSlug` from `@/auth/server-helpers` (member variant shipped in 4b); `FormField`, `DateInput`, `Button`, `Card` from `@sacco/ui`.
- Produces: `memberStatementRangeSchema` + `MemberStatementRangeInput` in `@sacco/schemas`; `/api/member/statement?from_date=&to_date=&format=` proxy; `/member/statements` page; "Statements" nav item between Fees and Profile.

- [ ] **Step 1: Write the failing tests**

Append to `admin/packages/schemas/src/__tests__/member.test.ts`:

```ts
import { memberStatementRangeSchema } from "../member";

describe("memberStatementRangeSchema", () => {
  it("accepts blanks and a valid range", () => {
    expect(memberStatementRangeSchema.safeParse({ from_date: "", to_date: "" }).success).toBe(true);
    expect(
      memberStatementRangeSchema.safeParse({ from_date: "2026-01-01", to_date: "2026-02-01" }).success,
    ).toBe(true);
  });

  it("rejects from after to", () => {
    const r = memberStatementRangeSchema.safeParse({ from_date: "2026-03-01", to_date: "2026-01-01" });
    expect(r.success).toBe(false);
  });
});
```

Create `admin/apps/portal/app/member/(authed)/statements/__tests__/StatementForm.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StatementForm } from "../_components/StatementForm";

const openSpy = vi.fn();

beforeEach(() => {
  openSpy.mockReset();
  vi.stubGlobal("open", openSpy);
});

describe("StatementForm", () => {
  it("opens the PDF proxy URL with the chosen range", async () => {
    const user = userEvent.setup();
    render(<StatementForm />);
    await user.type(screen.getByLabelText(/from/i), "2026-01-01");
    await user.type(screen.getByLabelText(/to/i), "2026-02-28");
    await user.click(screen.getByRole("button", { name: /download pdf/i }));
    await waitFor(() => expect(openSpy).toHaveBeenCalledTimes(1));
    const url = openSpy.mock.calls[0]![0] as string;
    expect(url).toContain("/api/member/statement?");
    expect(url).toContain("format=pdf");
    expect(url).toContain("from_date=2026-01-01");
    expect(url).toContain("to_date=2026-02-28");
  });

  it("opens the HTML preview without dates", async () => {
    const user = userEvent.setup();
    render(<StatementForm />);
    await user.click(screen.getByRole("button", { name: /preview in browser/i }));
    await waitFor(() => expect(openSpy).toHaveBeenCalledTimes(1));
    const url = openSpy.mock.calls[0]![0] as string;
    expect(url).toContain("format=html");
    expect(url).not.toContain("from_date");
  });

  it("blocks an inverted range", async () => {
    const user = userEvent.setup();
    render(<StatementForm />);
    await user.type(screen.getByLabelText(/from/i), "2026-03-01");
    await user.type(screen.getByLabelText(/to/i), "2026-01-01");
    await user.click(screen.getByRole("button", { name: /download pdf/i }));
    expect(await screen.findByText(/before/i)).toBeInTheDocument();
    expect(openSpy).not.toHaveBeenCalled();
  });
});
```

Note: check how `DateInput` is driven in existing tests (e.g. the KYC form tests) —
if `user.type` does not work against it, use the same interaction those tests use.

- [ ] **Step 2: Run tests to verify they fail**

Run (from `admin/`): `pnpm --filter @sacco/schemas test` → FAIL (`memberStatementRangeSchema` not exported), and `pnpm --filter @sacco/portal test -- StatementForm` → FAIL (component missing).

- [ ] **Step 3: Write the implementation**

Append to `admin/packages/schemas/src/member.ts` (import `z` is already there; `dateString` — check `./common` for the existing date validator used by KYC and reuse it; if it is named differently, adapt):

```ts
// Consolidated statement date range (both ends optional).
const optionalDate = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/, "Use YYYY-MM-DD")
  .or(z.literal(""));

export const memberStatementRangeSchema = z
  .object({
    from_date: optionalDate,
    to_date: optionalDate,
  })
  .refine(
    (v) => !v.from_date || !v.to_date || v.from_date <= v.to_date,
    { message: "The start date must be before the end date", path: ["to_date"] },
  );

export type MemberStatementRangeInput = z.infer<typeof memberStatementRangeSchema>;
```

Create `admin/apps/portal/app/api/member/statement/route.ts` (pattern copied from `app/api/credit/loans/[id]/statement-pdf/route.ts`):

```ts
// admin/apps/portal/app/api/member/statement/route.ts
import { NextResponse } from "next/server";
import { getServerAccessToken, getServerTenantSlug } from "@/auth/server-helpers";

const API_BASE =
  process.env["API_INTERNAL_URL"] ??
  process.env["NEXT_PUBLIC_API_BASE_URL"] ??
  "http://localhost:8000";

export async function GET(request: Request): Promise<NextResponse> {
  const slug = await getServerTenantSlug();
  const { accessToken } = await getServerAccessToken("member");
  if (!slug || !accessToken) {
    return NextResponse.json({ error: "No member session" }, { status: 401 });
  }

  const incoming = new URL(request.url);
  const upstream = new URL(`${API_BASE}/member/statement`);
  for (const key of ["from_date", "to_date", "format"]) {
    const value = incoming.searchParams.get(key);
    if (value) upstream.searchParams.set(key, value);
  }

  const r = await fetch(upstream, {
    headers: { Authorization: `Bearer ${accessToken}`, "X-Tenant-Slug": slug },
    cache: "no-store",
  });
  if (!r.ok) {
    return NextResponse.json({ error: "Failed to load statement" }, { status: r.status });
  }
  const isHtml = (r.headers.get("content-type") ?? "").startsWith("text/html");
  const body = await r.arrayBuffer();
  return new NextResponse(body, {
    status: 200,
    headers: isHtml
      ? { "Content-Type": "text/html; charset=utf-8" }
      : {
          "Content-Type": "application/pdf",
          "Content-Disposition": 'attachment; filename="member-statement.pdf"',
        },
  });
}
```

Note: verified — `getServerTenantSlug` is audience-agnostic (header/cookie) and
`getServerAccessToken("member")` itself resolves the slug the same way, so the
route as written matches the member flow.

Create `admin/apps/portal/app/member/(authed)/statements/_components/StatementForm.tsx`:

```tsx
"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button, Card, DateInput, FormField } from "@sacco/ui";
import {
  memberStatementRangeSchema,
  type MemberStatementRangeInput,
} from "@sacco/schemas";

function statementUrl(values: MemberStatementRangeInput, format: "pdf" | "html"): string {
  const params = new URLSearchParams({ format });
  if (values.from_date) params.set("from_date", values.from_date);
  if (values.to_date) params.set("to_date", values.to_date);
  return `/api/member/statement?${params.toString()}`;
}

export function StatementForm() {
  const form = useForm<MemberStatementRangeInput>({
    resolver: zodResolver(memberStatementRangeSchema),
    defaultValues: { from_date: "", to_date: "" },
  });

  const open = (format: "pdf" | "html") =>
    form.handleSubmit((values) => {
      window.open(statementUrl(values, format), "_blank", "noopener,noreferrer");
    });

  return (
    <Card className="max-w-xl space-y-4 p-6">
      <p className="text-[var(--text-secondary)]">
        Download a consolidated statement of your savings, shares, loans, and
        fees. Leave the dates blank for a full-history statement.
      </p>
      <form className="space-y-4">
        <FormField
          control={form.control}
          name="from_date"
          label="From"
          render={({ field, id, describedBy, invalid }) => (
            <DateInput
              id={id}
              aria-describedby={describedBy}
              aria-invalid={invalid}
              value={field.value ?? ""}
              onValueChange={field.onChange}
              onBlur={field.onBlur}
              name={field.name}
              ref={field.ref}
            />
          )}
        />
        <FormField
          control={form.control}
          name="to_date"
          label="To"
          render={({ field, id, describedBy, invalid }) => (
            <DateInput
              id={id}
              aria-describedby={describedBy}
              aria-invalid={invalid}
              value={field.value ?? ""}
              onValueChange={field.onChange}
              onBlur={field.onBlur}
              name={field.name}
              ref={field.ref}
            />
          )}
        />
        <div className="flex gap-3">
          <Button type="button" onClick={open("pdf")}>
            Download PDF
          </Button>
          <Button type="button" variant="secondary" onClick={open("html")}>
            Preview in browser
          </Button>
        </div>
      </form>
    </Card>
  );
}
```

Create `admin/apps/portal/app/member/(authed)/statements/page.tsx`:

```tsx
import { StatementForm } from "./_components/StatementForm";

export const metadata = { title: "Statements" };

export default function MemberStatementsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-[length:var(--text-h4)] font-semibold">Statements</h1>
      <StatementForm />
    </div>
  );
}
```

In `admin/apps/portal/src/components/shell/nav-config.tsx`: add `FileText` to the
lucide-react import and insert into `MEMBER_NAV` between Fees and Profile:

```tsx
      { label: "Statements", href: "/member/statements", icon: FileText },
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `admin/`): `pnpm --filter @sacco/schemas test && pnpm --filter @sacco/portal test -- StatementForm`
Expected: PASS.

- [ ] **Step 5: Lint, typecheck, commit**

Run (from `admin/`): `pnpm lint && pnpm typecheck`
Expected: clean.

```bash
git add "admin/apps/portal/app/api/member" "admin/apps/portal/app/member/(authed)/statements" admin/apps/portal/src/components/shell/nav-config.tsx admin/packages/schemas/src/member.ts admin/packages/schemas/src/__tests__/member.test.ts
git commit -m "feat(portal): member Statements page with PDF download + HTML preview"
```

---

### Task 5: Close-out — full suites + CLAUDE.md contract

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Backend suite**

Run: `python -m ruff check app/ tests/ && python -m mypy app/ && python -m pytest tests/modules/reporting/ tests/modules/members/ tests/modules/credit/ -q`
Expected: all clean/green. (Do NOT bundle `tests/core/` into the same invocation — the pre-existing credit↔core suite-order flake, noted 2026-07-10, is unrelated; run `python -m pytest tests/core/ -q` separately and expect green.)

- [ ] **Step 2: Admin suite**

Run (from `admin/`): `pnpm lint && pnpm typecheck && pnpm test`
Expected: all exit 0.

- [ ] **Step 3: Update CLAUDE.md**

In "## Member auth contracts (Phase 4a — do not violate)", append a bullet after the member-loan-apply bullet:

```markdown
- `GET /member/statement?from_date=&to_date=&format=pdf|html` (reporting module,
  `member_router`) renders the consolidated statement (savings + shares + loans +
  fees) on demand via `MemberStatementService` + WeasyPrint — live data, NOT
  materialized report runs. Always scoped to the current member (no id params).
  Empty data → valid empty-state PDF, 200; `from_date > to_date` → 422. The range
  filters transaction rows and fee assessments; loans always show the current
  snapshot + active schedule. The portal downloads through the
  `/api/member/statement` Next.js proxy (member Bearer token is server-side).
  Member nav: Dashboard / Savings / Shares / Loans / Fees / Statements / Profile.
```

Also update the "Member portal (Phase 4b)" section's first bullet: replace
"read-only, no member mutations, no statement PDF" with
"read-only except KYC submission + loan apply; consolidated statement PDF ships via `/member/statement`".

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): member consolidated statement contract (self-service increment 4)"
```

---

## Out of scope for this plan

- Async statement generation, notification delivery (Phase 3), object storage / caching
  of rendered PDFs.
- CSV/JSON formats for the member statement.
- Operator-facing consolidated statements (operators have the per-domain reports).
- Per-loan repayment history lines in the statement (the loan section is snapshot +
  schedule; `/member/loans/{id}/statement` already serves detailed loan history).
- This completes the 2026-06-29 member self-service phase.
