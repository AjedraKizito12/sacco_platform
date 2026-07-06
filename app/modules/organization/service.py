from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kyc.catalog import SACCO_KYC_CATALOG
from app.core.kyc.completion import KycCompletion, compute_completion
from app.modules.organization.models import OrganizationProfile
from app.platform_.kyc.service import SaccoKycRequirementsService

_VALUE_KEYS: tuple[str, ...] = tuple(f.key for f in SACCO_KYC_CATALOG)


class KycIncomplete(Exception):
    """Raised when verifying an organization whose KYC is not complete."""


class OrganizationKycService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self) -> OrganizationProfile:
        row = (
            await self._session.execute(select(OrganizationProfile).limit(1))
        ).scalar_one_or_none()
        if row is None:
            row = OrganizationProfile()
            self._session.add(row)
            await self._session.flush()
        return row

    def _values(self, row: OrganizationProfile) -> dict[str, object | None]:
        return {key: getattr(row, key) for key in _VALUE_KEYS}

    async def _completion(self, row: OrganizationProfile) -> KycCompletion:
        overrides = await SaccoKycRequirementsService(self._session).effective_required()
        # effective_required already resolves locked/default; pass as overrides
        # (locked keys map to True, which compute_completion re-applies safely).
        return compute_completion(self._values(row), SACCO_KYC_CATALOG, overrides)

    async def get_with_completion(self) -> tuple[OrganizationProfile, KycCompletion]:
        row = await self.get_or_create()
        return row, await self._completion(row)

    async def upsert(
        self, values: Mapping[str, object | None]
    ) -> tuple[OrganizationProfile, KycCompletion]:
        row = await self.get_or_create()
        changed = False
        for key in _VALUE_KEYS:
            if key in values and getattr(row, key) != values[key]:
                setattr(row, key, values[key])
                changed = True
        if changed and row.verified:
            row.verified = False
            row.verified_at = None
            row.verified_by_platform_user_id = None
        await self._session.flush()
        return row, await self._completion(row)

    async def set_verified(
        self, *, verified: bool, platform_user_id: uuid.UUID | None
    ) -> OrganizationProfile:
        row = await self.get_or_create()
        if verified:
            completion = await self._completion(row)
            if not completion.is_complete:
                raise KycIncomplete(
                    f"{len(completion.missing_required)} required field(s) missing"
                )
            row.verified = True
            row.verified_at = datetime.now(UTC)
            row.verified_by_platform_user_id = platform_user_id
        else:
            row.verified = False
            row.verified_at = None
            row.verified_by_platform_user_id = None
        await self._session.flush()
        return row
