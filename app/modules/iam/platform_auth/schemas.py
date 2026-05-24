"""Pydantic schemas for platform auth endpoints.

PlatformLoginRequest   — POST /platform/auth/token body
PlatformRefreshRequest — POST /platform/auth/refresh body
PlatformTokenResponse  — response body for token and refresh endpoints
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class PlatformLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class PlatformRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class PlatformTokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"  # noqa: S105
    expires_in: int  # seconds until access token expires


class PlatformPasswordResetRequestBody(BaseModel):
    email: EmailStr


class PlatformPasswordResetConfirmBody(BaseModel):
    token: str = Field(min_length=1)
    new_password: str = Field(min_length=1)
    # Note: hash_password() enforces the real minimum length (settings.auth_password_min_length).
    # A Pydantic min_length=1 here only catches completely empty strings.
