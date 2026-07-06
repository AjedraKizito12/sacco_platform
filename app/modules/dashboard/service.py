"""TenantDashboardStatsService — composes module services into one view.

Respects the modular-monolith boundary (CLAUDE.md rule 2): it depends only on
the public service interfaces of members/savings/credit, never their models.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.modules.credit.services.query import CreditQueryService
from app.modules.dashboard.schemas import TenantDashboardStatsOut
from app.modules.maker_checker.service import ApprovalService
from app.modules.members.service import MemberService
from app.modules.savings.service import SavingsService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class TenantDashboardStatsService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def compute(self) -> TenantDashboardStatsOut:
        members = await MemberService(self._s).count_by_status()
        total_savings = await SavingsService(self._s).total_balance_all_accounts()
        credit = CreditQueryService(self._s)
        portfolio = await credit.portfolio_summary()
        applications_pending = await credit.count_applications_awaiting_decision()
        approvals_pending = await ApprovalService(self._s).count_pending()
        return TenantDashboardStatsOut(
            members=members,
            total_members=sum(members.values()),
            total_savings=total_savings,
            loans_outstanding_principal=portfolio.outstanding_principal_total,
            loans_by_status=portfolio.loans_by_status,
            members_in_arrears=portfolio.members_in_arrears,
            approvals_pending=approvals_pending,
            applications_pending=applications_pending,
            last_updated=datetime.now(UTC),
        )
