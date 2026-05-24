"""Pydantic schemas for tenant auth endpoints.

TenantLoginRequest    — POST /auth/token body
TenantRefreshRequest  — POST /auth/refresh body
TenantTokenResponse   — response body for token and refresh endpoints

These are structurally identical to their platform_auth counterparts but
kept separate to avoid cross-module dependencies between platform_auth and
tenant_auth.
"""
from __future__ import annotations

import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003

from pydantic import BaseModel, EmailStr, Field


class TenantLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class TenantRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TenantTokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"  # noqa: S105
    expires_in: int  # seconds until access token expires


class TenantUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


class TenantPasswordResetRequestBody(BaseModel):
    email: EmailStr


class TenantPasswordResetConfirmBody(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=1)
