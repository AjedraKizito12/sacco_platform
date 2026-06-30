from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kyc.catalog import SACCO_KYC_CATALOG, FieldSpec
from app.platform_.kyc.models import SaccoKycRequirement

_LOCKED = {f.key for f in SACCO_KYC_CATALOG if f.locked}
_TOGGLEABLE = {f.key for f in SACCO_KYC_CATALOG if not f.locked}


class SaccoKycRequirementsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _overrides(self) -> dict[str, bool]:
        rows = (await self._session.execute(select(SaccoKycRequirement))).scalars().all()
        return {r.field_key: r.is_required for r in rows}

    async def effective_required(self) -> dict[str, bool]:
        overrides = await self._overrides()
        result: dict[str, bool] = {}
        for spec in SACCO_KYC_CATALOG:
            if spec.locked:
                result[spec.key] = True
            else:
                result[spec.key] = overrides.get(spec.key, spec.default_required)
        return result

    async def list_config(self) -> list[tuple[FieldSpec, bool]]:
        eff = await self.effective_required()
        return [(spec, eff[spec.key]) for spec in SACCO_KYC_CATALOG]

    async def replace(self, overrides: Mapping[str, bool]) -> None:
        """Replace all override rows. Locked and unknown keys are ignored;
        only non-locked catalog keys are persisted."""
        await self._session.execute(delete(SaccoKycRequirement))
        for key, required in overrides.items():
            if key in _TOGGLEABLE:
                self._session.add(
                    SaccoKycRequirement(field_key=key, is_required=bool(required))
                )
        await self._session.flush()
