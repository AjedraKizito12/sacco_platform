"""Pydantic schemas for /platform/tenants/{tenant_id}/users."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class TenantUserCreateIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    is_admin: bool = False


class TenantUserPatchIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    is_admin: bool | None = None


class TenantUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_admin: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # Always None on this endpoint — shadow users are filtered out in the list
    # path and looked up explicitly in the detail path (where a 404 is the
    # response if the target user is a shadow).
    impersonation_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class TenantUserCreateOut(BaseModel):
    user: TenantUserOut
    password_reset_token: str  # one-time; deliver out of band until Phase 3
    password_reset_expires_in: int  # seconds


class PasswordResetOut(BaseModel):
    user_id: uuid.UUID
    password_reset_token: str
    password_reset_expires_in: int
