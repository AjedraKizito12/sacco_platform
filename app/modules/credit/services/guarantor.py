# app/modules/credit/services/guarantor.py
"""GuarantorService — guarantor lifecycle + savings lien management."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import LoanGuarantor, LoanGuarantorLien, LoanProduct

_log = structlog.get_logger(__name__)


class GuarantorService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Nomination ────────────────────────────────────────────────────────────

    async def nominate(
        self,
        *,
        application_id: uuid.UUID,
        guarantor_member_ids: list[uuid.UUID],
        actor_id: uuid.UUID,
    ) -> list[LoanGuarantor]:
        """Nominate guarantors for a loan application."""
        from app.modules.credit.models import LoanApplication

        application = await self._session.get(LoanApplication, application_id)
        if application is None:
            raise ValueError(f"LoanApplication '{application_id}' not found")

        product = await self._session.get(LoanProduct, application.loan_product_id)
        assert product is not None

        if product.required_guarantors == 0:
            raise ValueError(
                f"Loan product '{product.name}' does not require guarantors"
            )
        if len(guarantor_member_ids) != product.required_guarantors:
            raise ValueError(
                f"Product requires {product.required_guarantors} guarantor(s); "
                f"got {len(guarantor_member_ids)}"
            )
        if len(set(guarantor_member_ids)) != len(guarantor_member_ids):
            raise ValueError("Duplicate guarantor member IDs")
        if application.member_id in set(guarantor_member_ids):
            raise ValueError("Borrower cannot be their own guarantor")

        lien_share = application.requested_amount / Decimal(str(product.required_guarantors))

        guarantors: list[LoanGuarantor] = []
        for member_id in guarantor_member_ids:
            lg = LoanGuarantor(
                loan_application_id=application_id,
                guarantor_member_id=member_id,
                guaranteed_amount=lien_share,
                status="nominated",
                idempotency_key=f"guarantee-{application_id}-{member_id}",
            )
            self._session.add(lg)
            guarantors.append(lg)

        await self._session.flush()
        _log.info(
            "credit.guarantors.nominated",
            application_id=str(application_id),
            count=len(guarantors),
        )
        return guarantors

    # ── Consent ───────────────────────────────────────────────────────────────

    async def accept(
        self,
        *,
        loan_guarantor_id: uuid.UUID,
        guarantor_member_id: uuid.UUID,
    ) -> LoanGuarantor:
        """Guarantor accepts nomination. actor must be the nominated guarantor."""
        lg = await self._session.get(LoanGuarantor, loan_guarantor_id)
        if lg is None:
            raise ValueError(f"LoanGuarantor '{loan_guarantor_id}' not found")
        if lg.guarantor_member_id != guarantor_member_id:
            raise ValueError(
                f"Member '{guarantor_member_id}' is not authorised to accept this guarantee"
            )
        if lg.status != "nominated":
            raise ValueError(f"Cannot accept guarantor with status '{lg.status}'")

        lg.status = "accepted"
        lg.consented_at = datetime.now(UTC)
        await self._session.flush()
        _log.info("credit.guarantor.accepted", loan_guarantor_id=str(loan_guarantor_id))
        return lg

    async def decline(
        self,
        *,
        loan_guarantor_id: uuid.UUID,
        guarantor_member_id: uuid.UUID,
    ) -> LoanGuarantor:
        """Guarantor declines nomination."""
        lg = await self._session.get(LoanGuarantor, loan_guarantor_id)
        if lg is None:
            raise ValueError(f"LoanGuarantor '{loan_guarantor_id}' not found")
        if lg.guarantor_member_id != guarantor_member_id:
            raise ValueError(
                f"Member '{guarantor_member_id}' is not authorised to decline this guarantee"
            )
        if lg.status != "nominated":
            raise ValueError(f"Cannot decline guarantor with status '{lg.status}'")

        lg.status = "declined"
        await self._session.flush()
        _log.info("credit.guarantor.declined", loan_guarantor_id=str(loan_guarantor_id))
        return lg

    # ── Lien lifecycle (called by disbursement/repayment/write-off) ───────────

    async def place_liens(
        self,
        *,
        loan_id: uuid.UUID,
        loan_application_id: uuid.UUID,
        principal_amount: Decimal,
    ) -> None:
        """Create lien rows for all accepted guarantors. No-op if none."""
        from app.modules.savings.service import SavingsService

        result = await self._session.execute(
            select(LoanGuarantor)
            .where(LoanGuarantor.loan_application_id == loan_application_id)
            .where(LoanGuarantor.status == "accepted")
        )
        guarantors = list(result.scalars().all())
        if not guarantors:
            return

        lien_share = principal_amount / Decimal(str(len(guarantors)))
        sav_svc = SavingsService(self._session)

        for g in guarantors:
            g.loan_id = loan_id
            savings_acct = await sav_svc.get_primary_account_for_member(
                g.guarantor_member_id
            )
            lien = LoanGuarantorLien(
                loan_guarantor_id=g.id,
                savings_account_id=savings_acct.id,
                original_lien=lien_share,
                current_lien=lien_share,
                is_active=True,
            )
            self._session.add(lien)

        await self._session.flush()
        _log.info("credit.guarantor_liens.placed", loan_id=str(loan_id), count=len(guarantors))

    async def adjust_liens(
        self,
        *,
        loan_id: uuid.UUID,
        principal_applied: Decimal,
        original_principal: Decimal,
    ) -> None:
        """Proportionally reduce liens after a repayment."""
        if principal_applied <= Decimal("0") or original_principal <= Decimal("0"):
            return

        result = await self._session.execute(
            select(LoanGuarantorLien)
            .join(LoanGuarantor, LoanGuarantorLien.loan_guarantor_id == LoanGuarantor.id)
            .where(LoanGuarantor.loan_id == loan_id)
            .where(LoanGuarantorLien.is_active.is_(True))
        )
        liens = list(result.scalars().all())
        if not liens:
            return

        fraction = principal_applied / original_principal
        for lien in liens:
            reduction = lien.original_lien * fraction
            lien.current_lien = max(Decimal("0"), lien.current_lien - reduction)

        await self._session.flush()

    async def release_liens(self, *, loan_id: uuid.UUID) -> None:
        """Release all liens on loan closure or write-off."""
        result = await self._session.execute(
            select(LoanGuarantorLien)
            .join(LoanGuarantor, LoanGuarantorLien.loan_guarantor_id == LoanGuarantor.id)
            .where(LoanGuarantor.loan_id == loan_id)
            .where(LoanGuarantorLien.is_active.is_(True))
        )
        liens = list(result.scalars().all())
        for lien in liens:
            lien.is_active = False
            lien.current_lien = Decimal("0")

        result2 = await self._session.execute(
            select(LoanGuarantor)
            .where(LoanGuarantor.loan_id == loan_id)
            .where(LoanGuarantor.status == "accepted")
        )
        for g in result2.scalars().all():
            g.status = "released"
            g.released_at = datetime.now(UTC)

        await self._session.flush()
        _log.info("credit.guarantor_liens.released", loan_id=str(loan_id))

    async def reactivate_liens(
        self,
        *,
        loan_id: uuid.UUID,
        restored_amount: Decimal,
    ) -> None:
        """Reactivate liens after write-off recovery."""
        result = await self._session.execute(
            select(LoanGuarantor)
            .where(LoanGuarantor.loan_id == loan_id)
            .where(LoanGuarantor.status == "released")
        )
        guarantors = list(result.scalars().all())
        if not guarantors:
            return

        lien_share = restored_amount / Decimal(str(len(guarantors)))

        for g in guarantors:
            g.status = "accepted"
            g.released_at = None

            result2 = await self._session.execute(
                select(LoanGuarantorLien)
                .where(LoanGuarantorLien.loan_guarantor_id == g.id)
                .where(LoanGuarantorLien.is_active.is_(False))
                .order_by(LoanGuarantorLien.created_at.desc())
                .limit(1)
            )
            lien = result2.scalar_one_or_none()
            if lien is not None:
                lien.current_lien = lien_share
                lien.is_active = True

        await self._session.flush()
        _log.info("credit.guarantor_liens.reactivated", loan_id=str(loan_id))

    async def all_accepted(self, *, application_id: uuid.UUID) -> bool:
        """Return True if all required guarantors have accepted (or none required)."""
        from app.modules.credit.models import LoanApplication
        application = await self._session.get(LoanApplication, application_id)
        if application is None:
            return True
        product = await self._session.get(LoanProduct, application.loan_product_id)
        assert product is not None
        if product.required_guarantors == 0:
            return True

        result = await self._session.execute(
            select(LoanGuarantor)
            .where(LoanGuarantor.loan_application_id == application_id)
            .where(LoanGuarantor.status != "accepted")
        )
        not_accepted = result.scalars().first()
        return not_accepted is None
