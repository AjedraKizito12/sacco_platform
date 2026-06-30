from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.core.kyc.completion import KycCompletion
from app.modules.organization.models import OrganizationProfile


class KycFieldStatusOut(BaseModel):
    key: str
    label: str
    required: bool
    present: bool


class KycCompletionOut(BaseModel):
    items: list[KycFieldStatusOut]
    required_total: int
    required_present: int
    percent: int
    missing_required: list[str]
    is_complete: bool

    @classmethod
    def from_completion(cls, c: KycCompletion) -> KycCompletionOut:
        return cls(
            items=[
                KycFieldStatusOut(key=i.key, label=i.label, required=i.required, present=i.present)
                for i in c.items
            ],
            required_total=c.required_total,
            required_present=c.required_present,
            percent=c.percent,
            missing_required=list(c.missing_required),
            is_complete=c.is_complete,
        )


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
