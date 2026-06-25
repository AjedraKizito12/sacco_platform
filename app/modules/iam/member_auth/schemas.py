"""Pydantic schemas for member auth endpoints (Phase 4a)."""
from __future__ import annotations

import uuid  # noqa: TC003
from datetime import date, datetime  # noqa: TC003

from pydantic import BaseModel, EmailStr, Field


class MemberLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class MemberRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class MemberTokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"  # noqa: S105
    expires_in: int  # seconds until the access token expires


class MemberOut(BaseModel):
    id: uuid.UUID
    member_number: str
    full_name: str
    email: str | None = None
    phone: str | None = None
    status: str
    date_of_birth: date
    gender: str
    joined_at: date | None = None
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


class MemberPasswordResetRequestBody(BaseModel):
    email: EmailStr


class MemberPasswordResetConfirmBody(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class EnablePortalAccessOut(BaseModel):
    """Returned to the operator. set_password_token is shown once, OOB-delivered."""

    member_id: uuid.UUID
    portal_enabled: bool
    set_password_token: str
    expires_in: int
