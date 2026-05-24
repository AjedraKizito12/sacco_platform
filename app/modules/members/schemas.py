from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


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
