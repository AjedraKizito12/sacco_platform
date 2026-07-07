"""TenantDashboardStatsService — composes module services into one view.

Respects the modular-monolith boundary (CLAUDE.md rule 2): it depends only on
the public service interfaces of members/savings/credit, never their models.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.month_series import as_cumulative, as_flow, month_keys
from app.modules.credit.services.query import CreditQueryService
from app.modules.dashboard.schemas import MonthPoint, TenantDashboardStatsOut
from app.modules.maker_checker.service import ApprovalService
from app.modules.members.service import MemberService
from app.modules.savings.service import SavingsService

# Trailing window for the dashboard trend charts.
_TREND_MONTHS = 6

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class TenantDashboardStatsService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def compute(self) -> TenantDashboardStatsOut:
        now = datetime.now(UTC)
        today = now.date()
        oldest = month_keys(_TREND_MONTHS, today=today)[0]
        since = datetime(int(oldest[:4]), int(oldest[5:7]), 1, tzinfo=UTC)
        month_start = datetime(today.year, today.month, 1, tzinfo=UTC)

        members_svc = MemberService(self._s)
        savings_svc = SavingsService(self._s)
        credit = CreditQueryService(self._s)

        members = await members_svc.count_by_status()
        members_new_this_month = await members_svc.count_created_since(month_start)
        total_savings = await savings_svc.total_balance_all_accounts()
        savings_movements = await savings_svc.monthly_net_movements(since=since)
        portfolio = await credit.portfolio_summary()
        disbursements = await credit.monthly_disbursements(since=since)
        applications_pending = await credit.count_applications_awaiting_decision()
        approvals_pending = await ApprovalService(self._s).count_pending()

        savings_trend = [
            MonthPoint(month=m, value=v)
            for m, v in as_cumulative(
                savings_movements, _TREND_MONTHS, today=today, current_total=total_savings
            )
        ]
        disbursement_trend = [
            MonthPoint(month=m, value=v)
            for m, v in as_flow(disbursements, _TREND_MONTHS, today=today)
        ]

        return TenantDashboardStatsOut(
            members=members,
            total_members=sum(members.values()),
            total_savings=total_savings,
            loans_outstanding_principal=portfolio.outstanding_principal_total,
            loans_by_status=portfolio.loans_by_status,
            members_in_arrears=portfolio.members_in_arrears,
            approvals_pending=approvals_pending,
            applications_pending=applications_pending,
            savings_trend=savings_trend,
            disbursement_trend=disbursement_trend,
            members_new_this_month=members_new_this_month,
            last_updated=now,
        )
