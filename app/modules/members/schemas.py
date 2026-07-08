from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.kyc.schemas import KycCompletionOut
from app.modules.members.models import KycSubmission

Gender = Literal["male", "female", "other"]
IdDocumentType = Literal["national_id", "passport", "driving_license"]


# ── Request schemas ───────────────────────────────────────────────────────────

class MemberIn(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    date_of_birth: date
    gender: Gender
    phone: str | None = None
    email: str | None = None
    physical_address: str | None = None
    national_id_number: str | None = None
    id_document_type: IdDocumentType | None = None
    id_document_number: str | None = None
    id_issued_date: date | None = None
    id_expiry_date: date | None = None


class StatusChangeIn(BaseModel):
    new_status: Literal["active", "suspended", "exited"]
    reason: str | None = None
    idempotency_key: str = Field(..., min_length=1, max_length=200)


# ── Response schemas ──────────────────────────────────────────────────────────

class MemberOut(BaseModel):
    id: uuid.UUID
    member_number: str
    full_name: str
    date_of_birth: date
    gender: str
    phone: str | None
    email: str | None
    physical_address: str | None
    national_id_number: str | None
    id_document_type: str | None
    id_document_number: str | None
    id_issued_date: date | None
    id_expiry_date: date | None
    status: str
    joined_at: date | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StatusChangeOut(BaseModel):
    approval_request_id: uuid.UUID
    status: str


class MemberKycOut(BaseModel):
    """Operator view: one member's KYC completion (values come from GET /members/{id})."""

    member_id: uuid.UUID
    completion: KycCompletionOut


class MemberKycValues(BaseModel):
    """The 11 editable (non-locked) member KYC fields — one shape for
    proposed snapshots, current values, and the member self view."""

    phone: str | None = None
    email: str | None = None
    physical_address: str | None = None
    national_id_number: str | None = None
    id_document_type: IdDocumentType | None = None
    id_document_number: str | None = None
    id_issued_date: date | None = None
    id_expiry_date: date | None = None
    next_of_kin_name: str | None = None
    next_of_kin_phone: str | None = None
    occupation: str | None = None

    model_config = {"from_attributes": True}


class KycSubmissionIn(MemberKycValues):
    """Proposed values — the FULL intended state of the editable fields.

    An omitted/None field clears the member value at approve time (the
    portal form prefills current values, so a blank is intentional).
    """


class KycSubmissionOut(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    status: str
    submitted_at: datetime
    reviewed_at: datetime | None
    rejection_reason: str | None
    proposed: MemberKycValues

    @classmethod
    def from_row(cls, s: KycSubmission) -> KycSubmissionOut:
        return cls(
            id=s.id,
            member_id=s.member_id,
            status=s.status,
            submitted_at=s.submitted_at,
            reviewed_at=s.reviewed_at,
            rejection_reason=s.rejection_reason,
            proposed=MemberKycValues.model_validate(s),
        )


class KycSubmissionListItemOut(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    member_number: str
    full_name: str
    status: str
    submitted_at: datetime


class KycSubmissionDetailOut(BaseModel):
    submission: KycSubmissionOut
    member_number: str
    full_name: str
    current: MemberKycValues


class KycRejectIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


class MemberSelfKycOut(BaseModel):
    """Member self view: completion + current values + latest submission."""

    completion: KycCompletionOut
    values: MemberKycValues
    latest_submission: KycSubmissionOut | None
