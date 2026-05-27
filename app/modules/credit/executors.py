# app/modules/credit/executors.py
"""Maker-checker executors for credit operations.

Import this module at app startup to register executors in approval_registry.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from app.modules.maker_checker.registry import approval_executor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@approval_executor("credit.approve_application")
async def execute_approve_application(session: AsyncSession, payload: dict) -> dict:
    """Executor: called by ApprovalService.approve() when quorum is met.

    payload keys (all strings — JSON round-tripped through JSONB):
        application_id: str (UUID)
        approved_amount: str (Decimal)
        approved_term_periods: str (int)
    """
    from app.modules.credit.models import LoanApplication

    application_id = uuid.UUID(payload["application_id"])
    approved_amount = Decimal(payload["approved_amount"])
    approved_term_periods = int(payload["approved_term_periods"])

    application = await session.get(LoanApplication, application_id)
    if application is None:
        raise ValueError(f"LoanApplication '{application_id}' not found in executor")

    # Idempotency guard — already approved on a prior executor call.
    if application.status == "approved":
        return {
            "application_id": str(application_id),
            "status": "approved",
        }

    application.status = "approved"
    application.approved_amount = approved_amount
    application.approved_term_periods = approved_term_periods
    await session.flush()

    return {
        "application_id": str(application_id),
        "status": "approved",
    }
