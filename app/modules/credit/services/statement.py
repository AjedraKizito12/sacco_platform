"""LoanStatementService — JSON statement assembly and WeasyPrint PDF rendering."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    import uuid

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
        """
        # 1. Load journal lines for this loan sub-ledger
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

        # 2. Load fee assessments for this loan
        fa_query = (
            select(FeeAssessment)
            .where(
                FeeAssessment.target_type == "loan",
                FeeAssessment.target_id == loan_id,
            )
            .order_by(FeeAssessment.assessed_at)
        )
        fee_rows = (await self._session.scalars(fa_query)).all()

        # 3. Build raw lines with timestamps for sorting
        raw_lines: list[tuple[datetime, StatementLine]] = []

        for jl, je in jl_rows:
            line_type = "other"
            for prefix, lt in _LINE_TYPE_MAP.items():
                if je.reference.startswith(prefix):
                    line_type = lt
                    break

            raw_lines.append((
                je.posted_at,
                StatementLine(
                    date=je.posted_at.date(),
                    line_type=line_type,
                    description=je.description,
                    debit=jl.debit_amount,
                    credit=jl.credit_amount,
                ),
            ))

        for fa in fee_rows:
            raw_lines.append((
                fa.assessed_at,
                StatementLine(
                    date=fa.assessed_at.date(),
                    line_type="penalty_assessed",
                    description=f"Fee assessed: {fa.amount}",
                    debit=fa.amount,
                    credit=Decimal("0"),
                ),
            ))

        # 4. Sort all lines chronologically
        raw_lines.sort(key=lambda x: x[0])

        # 5. Compute running_balance by replay over ALL lines first
        all_lines = [sl for _, sl in raw_lines]
        balance = Decimal("0")
        for sl in all_lines:
            balance = balance + sl.debit - sl.credit
            sl.running_balance = balance

        # 6. Apply date filter AFTER balance computation
        lines = all_lines
        if from_date is not None:
            lines = [sl for sl in lines if sl.date >= from_date]
        if to_date is not None:
            lines = [sl for sl in lines if sl.date <= to_date]

        return lines

    async def render_pdf(
        self,
        *,
        loan_id: uuid.UUID,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> bytes:
        """Render loan statement as PDF bytes via WeasyPrint."""
        from pathlib import Path

        import jinja2
        import weasyprint

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
            generated_at=datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC"),
        )

        pdf_bytes: bytes = weasyprint.HTML(string=html_str).write_pdf()
        return pdf_bytes
