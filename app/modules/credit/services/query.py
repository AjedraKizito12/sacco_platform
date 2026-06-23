# app/modules/credit/services/query.py
"""Read-only queries used by external callers (fees engine, reporting)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import Loan, LoanInstallment

_log = structlog.get_logger(__name__)

# Loans with a live principal balance — closed/written_off are excluded.
_ACTIVE_LOAN_STATUSES = ("disbursing", "disbursed", "in_arrears")


@dataclass(frozen=True)
class PortfolioSummary:
    """Read-only loan portfolio aggregate for the tenant dashboard."""

    outstanding_principal_total: Decimal
    loans_by_status: dict[str, int]
    members_in_arrears: int


class CreditQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def portfolio_summary(self) -> PortfolioSummary:
        """Aggregate the loan book for the dashboard in three small queries.

        - outstanding_principal_total: SUM(outstanding_principal) over loans
          in an active status (disbursing/disbursed/in_arrears). The snapshot
          column is authoritative for operational balance queries per the
          credit module contract.
        - loans_by_status: count grouped by every loans.status.
        - members_in_arrears: distinct members with at least one in_arrears loan.
        """
        outstanding = await self._session.scalar(
            select(func.coalesce(func.sum(Loan.outstanding_principal), Decimal("0")))
            .where(Loan.status.in_(_ACTIVE_LOAN_STATUSES))
        )

        by_status_result = await self._session.execute(
            select(Loan.status, func.count()).group_by(Loan.status)
        )
        loans_by_status = {row[0]: row[1] for row in by_status_result.all()}

        members_in_arrears = await self._session.scalar(
            select(func.count(func.distinct(Loan.member_id)))
            .where(Loan.status == "in_arrears")
        )

        return PortfolioSummary(
            outstanding_principal_total=Decimal(str(outstanding or 0)),
            loans_by_status=loans_by_status,
            members_in_arrears=int(members_in_arrears or 0),
        )

    async def find_loans_eligible_for_fee(
        self,
        *,
        as_of_date: date,
        min_days_past_due: int = 0,
    ) -> list[dict[str, Any]]:
        """Return loans with at least one overdue installment.

        Called by the fees engine's schedule job to determine which loans
        are eligible for a penalty fee type.

        Returns:
            List of dicts with keys:
              - loan_id: UUID
              - member_id: UUID
              - outstanding_principal: Decimal
              - days_past_due: int (days since earliest overdue installment)
        """
        rows = list(
            (
                await self._session.execute(
                    select(
                        Loan.id.label("loan_id"),
                        Loan.member_id,
                        Loan.outstanding_principal,
                        func.min(LoanInstallment.due_date).label("earliest_due"),
                    )
                    .join(LoanInstallment, LoanInstallment.loan_id == Loan.id)
                    .where(
                        Loan.status.in_(["disbursed", "in_arrears"]),
                        LoanInstallment.due_date < as_of_date,
                        LoanInstallment.status.in_(["pending", "partial", "overdue"]),
                    )
                    .group_by(Loan.id, Loan.member_id, Loan.outstanding_principal)
                )
            ).all()
        )

        result = []
        for row in rows:
            days_past_due = (as_of_date - row.earliest_due).days
            if days_past_due >= min_days_past_due:
                result.append(
                    {
                        "loan_id": row.loan_id,
                        "member_id": row.member_id,
                        "outstanding_principal": row.outstanding_principal,
                        "days_past_due": days_past_due,
                    }
                )
        return result
