"""Member KYC: per-tenant required-set service + completion helper.

Tenant-schema twin of app/platform_/kyc/service.py (which owns the
platform-global SACCO required set). Completion always goes through
app.core.kyc.compute_completion — never hand-rolled.
"""
from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kyc.catalog import MEMBER_KYC_CATALOG, FieldSpec
from app.core.kyc.completion import KycCompletion, compute_completion
from app.modules.members.models import Member, MemberKycRequirement

_TOGGLEABLE = {f.key for f in MEMBER_KYC_CATALOG if not f.locked}
_VALUE_KEYS: tuple[str, ...] = tuple(f.key for f in MEMBER_KYC_CATALOG)


class MemberKycRequirementsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _overrides(self) -> dict[str, bool]:
        rows = (
            await self._session.execute(select(MemberKycRequirement))
        ).scalars().all()
        return {r.field_key: r.is_required for r in rows}

    async def effective_required(self) -> dict[str, bool]:
        overrides = await self._overrides()
        result: dict[str, bool] = {}
        for spec in MEMBER_KYC_CATALOG:
            if spec.locked:
                result[spec.key] = True
            else:
                result[spec.key] = overrides.get(spec.key, spec.default_required)
        return result

    async def list_config(self) -> list[tuple[FieldSpec, bool]]:
        eff = await self.effective_required()
        return [(spec, eff[spec.key]) for spec in MEMBER_KYC_CATALOG]

    async def replace(self, overrides: Mapping[str, bool]) -> None:
        """Replace all override rows. Locked and unknown keys are ignored;
        only non-locked catalog keys are persisted."""
        await self._session.execute(delete(MemberKycRequirement))
        for key, required in overrides.items():
            if key in _TOGGLEABLE:
                self._session.add(
                    MemberKycRequirement(field_key=key, is_required=bool(required))
                )
        await self._session.flush()


def member_kyc_values(member: Member) -> dict[str, object | None]:
    """Catalog-keyed values for one member.

    getattr default handles catalog keys whose columns ship with increment 5
    (next_of_kin_name, next_of_kin_phone, occupation) — absent column reads
    as "not provided", which is the truth until the data can be collected.
    """
    return {key: getattr(member, key, None) for key in _VALUE_KEYS}


async def member_kyc_completion(
    session: AsyncSession, member: Member
) -> KycCompletion:
    overrides = await MemberKycRequirementsService(session).effective_required()
    return compute_completion(member_kyc_values(member), MEMBER_KYC_CATALOG, overrides)
