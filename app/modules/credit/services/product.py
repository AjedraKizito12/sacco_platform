# app/modules/credit/services/product.py
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import LoanProduct

_log = structlog.get_logger(__name__)

_VALID_INTEREST_METHODS = frozenset({"flat", "reducing_balance"})
_VALID_FREQUENCIES = frozenset({"weekly", "biweekly", "monthly", "quarterly", "lump_sum"})
_VALID_DESTINATIONS = frozenset({"member_savings", "cash", "internal_gl"})
_VALID_REPAYMENT_ALLOCATIONS = frozenset({"INTEREST_PRINCIPAL"})


class LoanProductService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        name: str,
        description: str | None = None,
        interest_method: str,
        annual_interest_rate: Decimal,
        repayment_frequency: str,
        max_term_periods: int,
        min_amount: Decimal,
        max_amount: Decimal,
        required_approvals: int = 1,
        disbursement_destinations: list[str],
        repayment_allocation: str = "INTEREST_PRINCIPAL",
        gl_principal_receivable_code: str,
        gl_interest_receivable_code: str,
        gl_interest_income_code: str,
        gl_loan_loss_expense_code: str | None = None,
        penalty_fee_type_code: str | None = None,
        write_off_threshold: Decimal = Decimal("0"),
        created_by: uuid.UUID,
    ) -> LoanProduct:
        """Create and persist a new loan product. Validates all business rules."""
        if interest_method not in _VALID_INTEREST_METHODS:
            raise ValueError(
                f"interest_method must be one of: {sorted(_VALID_INTEREST_METHODS)}"
            )
        if repayment_frequency not in _VALID_FREQUENCIES:
            raise ValueError(
                f"repayment_frequency must be one of: {sorted(_VALID_FREQUENCIES)}"
            )
        if annual_interest_rate < Decimal("0"):
            raise ValueError("annual_interest_rate must be >= 0")
        if min_amount <= Decimal("0"):
            raise ValueError("min_amount must be > 0")
        if max_amount < min_amount:
            raise ValueError("max_amount must be >= min_amount")
        if max_term_periods < 1:
            raise ValueError("max_term_periods must be >= 1")
        if required_approvals < 1:
            raise ValueError("required_approvals must be >= 1")
        if write_off_threshold < Decimal("0"):
            raise ValueError("write_off_threshold must be >= 0")
        if repayment_allocation not in _VALID_REPAYMENT_ALLOCATIONS:
            raise ValueError(
                f"repayment_allocation must be one of: {sorted(_VALID_REPAYMENT_ALLOCATIONS)}"
            )
        if not disbursement_destinations:
            raise ValueError("disbursement_destinations must not be empty")
        invalid_destinations = set(disbursement_destinations) - _VALID_DESTINATIONS
        if invalid_destinations:
            raise ValueError(
                f"Invalid disbursement_destinations: {invalid_destinations}. "
                f"Valid values: {sorted(_VALID_DESTINATIONS)}"
            )

        product = LoanProduct(
            name=name,
            description=description,
            interest_method=interest_method,
            annual_interest_rate=annual_interest_rate,
            repayment_frequency=repayment_frequency,
            max_term_periods=max_term_periods,
            min_amount=min_amount,
            max_amount=max_amount,
            required_approvals=required_approvals,
            disbursement_destinations=disbursement_destinations,
            repayment_allocation=repayment_allocation,
            gl_principal_receivable_code=gl_principal_receivable_code,
            gl_interest_receivable_code=gl_interest_receivable_code,
            gl_interest_income_code=gl_interest_income_code,
            gl_loan_loss_expense_code=gl_loan_loss_expense_code,
            penalty_fee_type_code=penalty_fee_type_code,
            write_off_threshold=write_off_threshold,
        )
        self._session.add(product)
        await self._session.flush()
        _log.info(
            "loan_product.created",
            product_id=str(product.id),
            name=name,
            interest_method=interest_method,
            created_by=str(created_by),
        )
        return product

    async def get(self, product_id: uuid.UUID) -> LoanProduct:
        p = await self._session.get(LoanProduct, product_id)
        if p is None:
            raise ValueError(f"LoanProduct '{product_id}' not found")
        return p

    async def list(self, *, include_inactive: bool = False) -> list[LoanProduct]:
        q = select(LoanProduct).order_by(LoanProduct.name)
        if not include_inactive:
            q = q.where(LoanProduct.is_active.is_(True))
        result = await self._session.execute(q)
        return list(result.scalars().all())

    async def update(
        self,
        product_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        penalty_fee_type_code: str | None = None,
        write_off_threshold: Decimal | None = None,
        updated_by: uuid.UUID,
    ) -> LoanProduct:
        """Patch non-financial fields only. Financial/structural fields (rates,
        amounts, GL codes, interest method) are immutable after creation to
        protect the snapshots on existing loan rows."""
        p = await self.get(product_id)
        if name is not None:
            p.name = name
        if description is not None:
            p.description = description
        if penalty_fee_type_code is not None:
            p.penalty_fee_type_code = penalty_fee_type_code
        if write_off_threshold is not None:
            if write_off_threshold < Decimal("0"):
                raise ValueError("write_off_threshold must be >= 0")
            p.write_off_threshold = write_off_threshold
        await self._session.flush()
        _log.info(
            "loan_product.updated",
            product_id=str(product_id),
            updated_by=str(updated_by),
        )
        return p

    async def deactivate(
        self, product_id: uuid.UUID, *, deactivated_by: uuid.UUID
    ) -> LoanProduct:
        p = await self.get(product_id)
        p.is_active = False
        await self._session.flush()
        _log.info(
            "loan_product.deactivated",
            product_id=str(product_id),
            deactivated_by=str(deactivated_by),
        )
        return p
