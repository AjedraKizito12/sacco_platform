# app/modules/credit/services/application.py
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import LoanApplication

_log = structlog.get_logger(__name__)


class LoanApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def submit(
        self,
        *,
        loan_product_id: uuid.UUID,
        member_id: uuid.UUID,
        requested_amount: Decimal,
        requested_term_periods: int,
        purpose: str | None = None,
        disbursement_destination: str,
        disbursement_account_id: uuid.UUID | None = None,
        submitted_by: uuid.UUID,
        idempotency_key: str,
    ) -> LoanApplication:
        """Submit a loan application and create a maker-checker approval request.

        Idempotent: returns the existing application if idempotency_key already used.
        """
        # Idempotency guard.
        existing = await self._session.scalar(
            select(LoanApplication).where(
                LoanApplication.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            _log.info(
                "credit.application.submit.idempotent_hit",
                idempotency_key=idempotency_key,
            )
            return existing

        # Validate product.
        from app.modules.credit.services.product import LoanProductService

        product_svc = LoanProductService(self._session)
        product = await product_svc.get(loan_product_id)
        if not product.is_active:
            raise ValueError(f"LoanProduct '{loan_product_id}' is not active")

        # Validate amounts and terms.
        if requested_amount < product.min_amount:
            raise ValueError(
                f"requested_amount {requested_amount} is below product min_amount {product.min_amount}"
            )
        if requested_amount > product.max_amount:
            raise ValueError(
                f"requested_amount {requested_amount} exceeds product max_amount {product.max_amount}"
            )
        if requested_term_periods > product.max_term_periods:
            raise ValueError(
                f"requested_term_periods {requested_term_periods} exceeds product max_term_periods "
                f"{product.max_term_periods}"
            )
        if disbursement_destination not in product.disbursement_destinations:
            raise ValueError(
                f"disbursement_destination '{disbursement_destination}' is not allowed by product. "
                f"Allowed: {product.disbursement_destinations}"
            )

        # Create application row.
        application = LoanApplication(
            loan_product_id=loan_product_id,
            member_id=member_id,
            requested_amount=requested_amount,
            requested_term_periods=requested_term_periods,
            purpose=purpose,
            disbursement_destination=disbursement_destination,
            disbursement_account_id=disbursement_account_id,
            status="submitted",
            idempotency_key=idempotency_key,
        )
        self._session.add(application)
        await self._session.flush()

        # Submit approval request.
        from app.modules.maker_checker.service import ApprovalService

        approval_svc = ApprovalService(self._session)
        request = await approval_svc.submit(
            operation_type="credit.approve_application",
            payload={
                "application_id": str(application.id),
                "approved_amount": str(requested_amount),
                "approved_term_periods": str(requested_term_periods),
            },
            requested_by=submitted_by,
            required_approvals=product.required_approvals,
        )
        application.approval_request_id = request.id
        await self._session.flush()

        _log.info(
            "credit.application.submitted",
            application_id=str(application.id),
            member_id=str(member_id),
            amount=str(requested_amount),
            approval_request_id=str(request.id),
        )
        return application

    async def get(self, application_id: uuid.UUID) -> LoanApplication:
        a = await self._session.get(LoanApplication, application_id)
        if a is None:
            raise ValueError(f"LoanApplication '{application_id}' not found")
        return a

    async def list(
        self,
        *,
        member_id: uuid.UUID | None = None,
        status: str | None = None,
    ) -> list[LoanApplication]:
        q = select(LoanApplication).order_by(LoanApplication.created_at.desc())
        if member_id is not None:
            q = q.where(LoanApplication.member_id == member_id)
        if status is not None:
            q = q.where(LoanApplication.status == status)
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def withdraw(
        self,
        *,
        application_id: uuid.UUID,
        withdrawn_by: uuid.UUID,
    ) -> LoanApplication:
        """Withdraw a pending application.

        Delegates to ApprovalService.cancel() which enforces:
        - Only the original submitter can withdraw (self-check)
        - Cannot withdraw after any approver has acted
        """
        application = await self.get(application_id)

        if application.status in ("approved", "rejected", "withdrawn", "cancelled"):
            raise ValueError(
                f"Cannot withdraw application with status '{application.status}'"
            )

        if application.approval_request_id is not None:
            from app.modules.maker_checker.service import ApprovalService

            approval_svc = ApprovalService(self._session)
            await approval_svc.cancel(
                request_id=application.approval_request_id,
                requested_by=withdrawn_by,
            )

        application.status = "withdrawn"
        await self._session.flush()
        _log.info(
            "credit.application.withdrawn",
            application_id=str(application_id),
            withdrawn_by=str(withdrawn_by),
        )
        return application

    async def reject(
        self,
        *,
        application_id: uuid.UUID,
        rejected_by: uuid.UUID,
        reason: str | None = None,
    ) -> LoanApplication:
        """Reject a pending application via ApprovalService.

        ApprovalService.reject() enforces self-rejection is forbidden.
        """
        application = await self.get(application_id)

        if application.status not in ("submitted", "under_review"):
            raise ValueError(
                f"Cannot reject application with status '{application.status}'"
            )

        if application.approval_request_id is not None:
            from app.modules.maker_checker.service import ApprovalService

            approval_svc = ApprovalService(self._session)
            await approval_svc.reject(
                request_id=application.approval_request_id,
                actor_user_id=rejected_by,
                reason=reason,
            )

        application.status = "rejected"
        application.rejection_reason = reason
        application.decided_by = rejected_by
        application.decided_at = datetime.now(UTC)
        await self._session.flush()
        _log.info(
            "credit.application.rejected",
            application_id=str(application_id),
            rejected_by=str(rejected_by),
        )
        return application
