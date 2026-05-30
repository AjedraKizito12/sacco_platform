from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fees.models import FeeAssessment, FeeCollection, FeeType

_log = structlog.get_logger(__name__)

_SYSTEM_ACTOR = uuid.UUID("00000000-0000-0000-0000-000000000000")


class FeeAssessmentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def assess(
        self,
        *,
        fee_type: FeeType,
        target_type: str,
        target_id: uuid.UUID,
        period_start: date,
        period_end: date | None,
        triggered_by_event_id: uuid.UUID | None,
        actor: uuid.UUID,
        idempotency_key: str,
    ) -> FeeAssessment:
        """Create a fee assessment. Idempotent via UNIQUE(fee_type_id, target_type, target_id, period_start).

        Posts assessment GL entry (Dr receivable, Cr income) in the same transaction.
        If fee_type.requires_collection=True, calls FeeCollectionService.auto_collect() inline.
        """
        # Idempotency: return existing if already assessed for this period.
        existing = await self._session.scalar(
            select(FeeAssessment).where(
                FeeAssessment.fee_type_id == fee_type.id,
                FeeAssessment.target_type == target_type,
                FeeAssessment.target_id == target_id,
                FeeAssessment.period_start == period_start,
            )
        )
        if existing is not None:
            _log.info("fees.assess.idempotent_hit", fee_type_code=fee_type.code)
            return existing

        # Resolve GL account IDs from codes.
        from app.modules.ledger.models import ChartOfAccount
        from app.modules.ledger.service import LedgerService

        income_account = await self._session.scalar(
            select(ChartOfAccount).where(ChartOfAccount.code == fee_type.gl_income_account_code)
        )
        if income_account is None:
            raise ValueError(
                f"GL income account '{fee_type.gl_income_account_code}' not found"
            )
        receivable_account = await self._session.scalar(
            select(ChartOfAccount).where(ChartOfAccount.code == fee_type.gl_receivable_account_code)
        )
        if receivable_account is None:
            raise ValueError(
                f"GL receivable account '{fee_type.gl_receivable_account_code}' not found"
            )

        # Assessment GL entry: Dr receivable, Cr income.
        ledger_svc = LedgerService(self._session)
        entry = await ledger_svc.post_journal_entry(
            reference=f"FEE-ASSESS-{fee_type.code}-{target_id}",
            description=f"Fee assessment: {fee_type.name} ({period_start})",
            posted_by=actor,
            idempotency_key=f"fee-assess-{idempotency_key}",
            lines=[
                {
                    "account_id": receivable_account.id,
                    "debit_amount": fee_type.amount,
                    "credit_amount": Decimal("0"),
                },
                {
                    "account_id": income_account.id,
                    "debit_amount": Decimal("0"),
                    "credit_amount": fee_type.amount,
                },
            ],
        )

        assessment = FeeAssessment(
            fee_type_id=fee_type.id,
            target_type=target_type,
            target_id=target_id,
            period_start=period_start,
            period_end=period_end,
            amount=fee_type.amount,
            currency=fee_type.currency,
            status="assessed",
            journal_entry_id=entry.id,
            triggered_by_event_id=triggered_by_event_id,
        )
        self._session.add(assessment)
        await self._session.flush()

        _log.info(
            "fees.assessed",
            fee_type_code=fee_type.code,
            target_type=target_type,
            target_id=str(target_id),
            amount=str(fee_type.amount),
        )

        # Auto-collect if configured.
        if fee_type.requires_collection:
            coll_svc = FeeCollectionService(self._session)
            await coll_svc.auto_collect(
                assessment=assessment,
                fee_type=fee_type,
                receivable_account_id=receivable_account.id,
                idempotency_key=idempotency_key,
            )

        return assessment

    async def get_assessment(self, assessment_id: uuid.UUID) -> FeeAssessment:
        a = await self._session.get(FeeAssessment, assessment_id)
        if a is None:
            raise ValueError(f"FeeAssessment '{assessment_id}' not found")
        return a

    async def list_assessments(
        self,
        *,
        status: str | None = None,
        target_type: str | None = None,
        target_id: uuid.UUID | None = None,
        fee_type_code: str | None = None,
    ) -> list[FeeAssessment]:
        q = select(FeeAssessment).order_by(FeeAssessment.assessed_at.desc())
        if status:
            q = q.where(FeeAssessment.status == status)
        if target_type:
            q = q.where(FeeAssessment.target_type == target_type)
        if target_id:
            q = q.where(FeeAssessment.target_id == target_id)
        if fee_type_code:
            q = q.join(FeeType).where(FeeType.code == fee_type_code)
        result = await self._session.execute(q)
        return list(result.scalars().all())


class FeeCollectionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def auto_collect(
        self,
        *,
        assessment: FeeAssessment,
        fee_type: FeeType,
        receivable_account_id: uuid.UUID,
        idempotency_key: str,
    ) -> FeeCollection | None:
        """Attempt auto-collection from member's primary savings account.

        Callable only from FeeAssessmentService. Not an API route.
        Uses on_insufficient_funds='partial' — partial collection is a first-class outcome.
        """
        from app.modules.savings.service import SavingsService

        savings_svc = SavingsService(self._session)
        savings_account = await savings_svc.get_primary_account_for_member(assessment.target_id)

        if savings_account is None:
            _log.info(
                "fees.auto_collect.no_savings_account",
                assessment_id=str(assessment.id),
            )
            return None

        result = await savings_svc.system_debit(
            savings_account_id=savings_account.id,
            amount=assessment.amount,
            reason="FEE_COLLECTION",
            source_module="fees",
            source_id=assessment.id,
            actor=_SYSTEM_ACTOR,
            idempotency_key=f"fee-collect-{idempotency_key}",
            contra_account_id=receivable_account_id,
            narration=f"Auto-collection: {fee_type.name}",
            on_insufficient_funds="partial",
        )

        if result.status == "zero":
            _log.info(
                "fees.auto_collect.zero_balance",
                assessment_id=str(assessment.id),
            )
            return None

        collection = FeeCollection(
            fee_assessment_id=assessment.id,
            amount=result.debited_amount,
            method="savings_deduction",
            collected_by=_SYSTEM_ACTOR,
            journal_entry_id=result.journal_entry_id,
            idempotency_key=f"fee-collect-{idempotency_key}",
            source_module="fees",
            source_id=assessment.id,
        )
        self._session.add(collection)

        if result.shortfall_amount == Decimal("0"):
            assessment.status = "paid"
            assessment.paid_at = datetime.now(UTC)
        else:
            assessment.status = "partially_paid"

        await self._session.flush()
        _log.info(
            "fees.collected",
            assessment_id=str(assessment.id),
            collected=str(result.debited_amount),
            shortfall=str(result.shortfall_amount),
        )
        return collection

    async def collect(
        self,
        *,
        assessment_id: uuid.UUID,
        amount: Decimal,
        method: str,
        collected_by: uuid.UUID,
        idempotency_key: str,
        contra_account_id: uuid.UUID,
    ) -> FeeCollection:
        """Manual collection (cash or journal_voucher). Called from API."""
        existing = await self._session.scalar(
            select(FeeCollection).where(FeeCollection.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing

        assessment_svc = FeeAssessmentService(self._session)
        assessment = await assessment_svc.get_assessment(assessment_id)

        if assessment.status in ("paid", "waived", "cancelled"):
            raise ValueError(
                f"Assessment '{assessment_id}' has status '{assessment.status}' and cannot be collected"
            )

        # Resolve receivable account.
        from app.modules.ledger.models import ChartOfAccount
        from app.modules.ledger.service import LedgerService

        ft = await self._session.get(FeeType, assessment.fee_type_id)
        if ft is None:
            raise ValueError(f"FeeType for assessment '{assessment_id}' not found")

        receivable_account = await self._session.scalar(
            select(ChartOfAccount).where(ChartOfAccount.code == ft.gl_receivable_account_code)
        )
        if receivable_account is None:
            raise ValueError(f"GL receivable account '{ft.gl_receivable_account_code}' not found")

        # Collection GL entry: Dr contra (cash), Cr receivable.
        ledger_svc = LedgerService(self._session)
        entry = await ledger_svc.post_journal_entry(
            reference=f"FEE-COLL-{assessment_id}",
            description=f"Fee collection: {ft.name}",
            posted_by=collected_by,
            idempotency_key=f"fee-manual-collect-{idempotency_key}",
            lines=[
                {
                    "account_id": contra_account_id,
                    "debit_amount": amount,
                    "credit_amount": Decimal("0"),
                },
                {
                    "account_id": receivable_account.id,
                    "debit_amount": Decimal("0"),
                    "credit_amount": amount,
                },
            ],
        )

        # Recompute total collected to update assessment status.
        # Query BEFORE adding the new collection to avoid double-counting with autoflush.
        all_collections = await self._session.execute(
            select(FeeCollection).where(FeeCollection.fee_assessment_id == assessment_id)
        )
        total_collected = sum(c.amount for c in all_collections.scalars().all()) + amount

        collection = FeeCollection(
            fee_assessment_id=assessment_id,
            amount=amount,
            method=method,
            collected_by=collected_by,
            journal_entry_id=entry.id,
            idempotency_key=idempotency_key,
            source_module="fees",
            source_id=assessment_id,
        )
        self._session.add(collection)

        if total_collected >= assessment.amount:
            assessment.status = "paid"
            assessment.paid_at = datetime.now(UTC)
        else:
            assessment.status = "partially_paid"

        await self._session.flush()
        return collection

    async def list_collections(self, assessment_id: uuid.UUID) -> list[FeeCollection]:
        result = await self._session.execute(
            select(FeeCollection)
            .where(FeeCollection.fee_assessment_id == assessment_id)
            .order_by(FeeCollection.collected_at)
        )
        return list(result.scalars().all())
