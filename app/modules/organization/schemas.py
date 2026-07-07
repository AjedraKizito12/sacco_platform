from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.core.kyc.completion import KycCompletion
from app.core.kyc.schemas import KycCompletionOut, KycFieldStatusOut
from app.modules.organization.models import OrganizationProfile

__all__ = [
    "KycCompletionOut",
    "KycFieldStatusOut",
    "OrganizationKycOut",
    "OrganizationKycValuesIn",
    "OrganizationKycValuesOut",
]


class OrganizationKycValuesIn(BaseModel):
    legal_name: str | None = None
    registration_number: str | None = None
    registered_address: str | None = None
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    registration_date: date | None = None
    regulator_name: str | None = None
    license_number: str | None = None
    tax_id: str | None = None
    primary_contact_phone: str | None = None
    postal_address: str | None = None
    district_region: str | None = None
    country: str | None = None


class OrganizationKycValuesOut(OrganizationKycValuesIn):
    model_config = {"from_attributes": True}


class OrganizationKycOut(BaseModel):
    values: OrganizationKycValuesOut
    verified: bool
    verified_at: datetime | None
    verified_by_platform_user_id: uuid.UUID | None
    completion: KycCompletionOut

    @classmethod
    def from_row_and_completion(
        cls, row: OrganizationProfile, completion: KycCompletion
    ) -> OrganizationKycOut:
        return cls(
            values=OrganizationKycValuesOut.model_validate(row),
            verified=bool(row.verified),
            verified_at=row.verified_at,
            verified_by_platform_user_id=row.verified_by_platform_user_id,
            completion=KycCompletionOut.from_completion(completion),
        )
