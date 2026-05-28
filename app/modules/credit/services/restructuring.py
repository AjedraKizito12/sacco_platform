# app/modules/credit/services/restructuring.py
"""LoanRestructuringService — term extension and payment holiday (maker-checker)."""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import Loan, LoanInstallment, LoanRestructuring
from app.modules.credit.services._schedule import compute_schedule
from app.modules.maker_checker.service import ApprovalService

_log = structlog.get_logger(__name__)

# Mapping from repayment_frequency to months per period (for payment_holiday date shifting)
_FREQ_MONTHS: dict[str, int] = {
    "weekly": 0,  # uses weeks, handled separately
    "biweekly": 0,  # uses weeks
    "monthly": 1,
    "quarterly": 3,
    "lump_sum": 1,
}

_FREQ_WEEKS: dict[str, int] = {
    "weekly": 1,
    "biweekly": 2,
}


def _shift_date(d: date, frequency: str, periods: int) -> date:
    """Shift a date forward by N periods based on repayment_frequency."""
    from datetime import timedelta

    from dateutil.relativedelta import relativedelta  # type: ignore[import-untyped]

    if frequency in _FREQ_WEEKS:
        return d + timedelta(weeks=_FREQ_WEEKS[frequency] * periods)
    months = _FREQ_MONTHS.get(frequency, 1)
    return d + relativedelta(months=months * periods)


class LoanRestructuringService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def restructure(
        self,
        *,
        loan_id: uuid.UUID,
        restructuring_type: str,
        periods_added: int,
        reason: str,
        actor_id: uuid.UUID,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Submit restructuring for maker-checker approval (quorum=2).

        Returns dict with 'approval_request_id'.
        Raises ValueError for invalid loan status, type, or periods_added.
        """
        loan = await self._session.get(Loan, loan_id)
        if loan is None:
            raise ValueError(f"Loan '{loan_id}' not found")
        if loan.status not in ("disbursed", "in_arrears"):
            raise ValueError(
                f"Cannot restructure loan with status '{loan.status}'"
            )
        if restructuring_type not in ("term_extension", "payment_holiday"):
            raise ValueError(f"Invalid restructuring_type '{restructuring_type}'")
        if periods_added < 1:
            raise ValueError("periods_added must be >= 1")

        approval_svc = ApprovalService(self._session)
        request = await approval_svc.submit(
            operation_type="credit.restructure_schedule",
            payload={
                "loan_id": str(loan_id),
                "restructuring_type": restructuring_type,
                "periods_added": periods_added,
                "reason": reason,
                "idempotency_key": idempotency_key,
            },
            requested_by=actor_id,
            required_approvals=2,
        )
        # Back-fill approval_request_id into the payload now that request.id is known.
        request.payload = {**request.payload, "approval_request_id": str(request.id)}
        await self._session.flush()

        _log.info(
            "credit.restructuring.submitted",
            loan_id=str(loan_id),
            type=restructuring_type,
            approval_request_id=str(request.id),
        )
        return {"approval_request_id": request.id}

    async def _execute_restructuring(
        self,
        *,
        loan_id: uuid.UUID,
        restructuring_type: str,
        periods_added: int,
        reason: str,
        actor_id: uuid.UUID,
        idempotency_key: str,
        approval_request_id: uuid.UUID | None,
    ) -> LoanRestructuring:
        """Execute restructuring: supersede unpaid installments, write new schedule.

        Called by the approval executor after quorum is reached.
        """
        from app.core.outbox import EventPublisher

        # ── Idempotency guard ─────────────────────────────────────────────────
        existing = await self._session.scalar(
            select(LoanRestructuring).where(
                LoanRestructuring.idempotency_key == idempotency_key
            )
        )
        if existing is not None:
            return existing

        # ── Lock loan row ─────────────────────────────────────────────────────
        loan = await self._session.scalar(
            select(Loan).where(Loan.id == loan_id).with_for_update()
        )
        if loan is None:
            raise ValueError(f"Loan '{loan_id}' not found")

        # ── Fetch active (non-superseded) installments ────────────────────────
        result = await self._session.execute(
            select(LoanInstallment)
            .where(LoanInstallment.loan_id == loan_id)
            .where(LoanInstallment.is_superseded.is_(False))
            .order_by(LoanInstallment.period_number)
        )
        active_installments = list(result.scalars().all())

        # Separate paid vs unpaid
        paid = [i for i in active_installments if i.status == "paid"]
        unpaid = [i for i in active_installments if i.status != "paid"]
        last_paid_period = max((i.period_number for i in paid), default=0)

        # Mark unpaid installments as superseded
        for inst in unpaid:
            inst.is_superseded = True

        new_installments: list[LoanInstallment] = []
        freq = loan.repayment_frequency

        if restructuring_type == "term_extension":
            remaining_periods = len(unpaid) + periods_added
            new_term_periods = last_paid_period + remaining_periods

            # Recompute schedule from outstanding_principal over remaining+added periods
            today = date.today()
            schedule = compute_schedule(
                principal=loan.outstanding_principal,
                annual_interest_rate=loan.annual_interest_rate,
                interest_method=loan.interest_method,
                repayment_frequency=freq,
                term_periods=remaining_periods,
                disbursement_date=today,
            )
            for idx, row in enumerate(schedule):
                inst = LoanInstallment(
                    loan_id=loan_id,
                    period_number=last_paid_period + 1 + idx,
                    due_date=row.due_date,
                    principal_due=row.principal_due,
                    interest_due=row.interest_due,
                    total_due=row.total_due,
                    restructuring_id=None,  # set after LoanRestructuring is created
                )
                self._session.add(inst)
                new_installments.append(inst)

            new_maturity_date = schedule[-1].due_date if schedule else date.today()

        else:  # payment_holiday
            new_term_periods = loan.term_periods + periods_added
            if not unpaid:
                new_maturity_date = loan.maturity_date or date.today()
            else:
                for orig in unpaid:
                    shifted_date = _shift_date(orig.due_date, freq, periods_added)
                    inst = LoanInstallment(
                        loan_id=loan_id,
                        period_number=orig.period_number + periods_added,
                        due_date=shifted_date,
                        principal_due=orig.principal_due,
                        interest_due=orig.interest_due,
                        total_due=orig.total_due,
                        restructuring_id=None,
                    )
                    self._session.add(inst)
                    new_installments.append(inst)
                new_maturity_date = (
                    new_installments[-1].due_date if new_installments else date.today()
                )

        # ── Update loan ───────────────────────────────────────────────────────
        loan.term_periods = new_term_periods
        loan.maturity_date = new_maturity_date
        await self._session.flush()

        # ── Create restructuring record ───────────────────────────────────────
        restructuring = LoanRestructuring(
            loan_id=loan_id,
            restructuring_type=restructuring_type,
            periods_added=periods_added,
            new_term_periods=new_term_periods,
            new_maturity_date=new_maturity_date,
            reason=reason,
            approval_request_id=approval_request_id,
            executed_by=actor_id,
            executed_at=datetime.now(UTC),
            idempotency_key=idempotency_key,
        )
        self._session.add(restructuring)
        await self._session.flush()

        # Tag new installments with restructuring_id
        for inst in new_installments:
            inst.restructuring_id = restructuring.id

        await self._session.flush()

        # ── Publish event ─────────────────────────────────────────────────────
        await EventPublisher.publish(
            self._session,
            aggregate_type="loan",
            aggregate_id=loan_id,
            event_type="LoanRestructured",
            payload={
                "loan_id": str(loan_id),
                "restructuring_id": str(restructuring.id),
                "type": restructuring_type,
                "periods_added": periods_added,
            },
        )

        _log.info(
            "credit.restructuring.executed",
            loan_id=str(loan_id),
            restructuring_id=str(restructuring.id),
            type=restructuring_type,
        )
        return restructuring
