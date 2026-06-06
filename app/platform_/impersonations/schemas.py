"""Pydantic schemas for the impersonation API surface.

ImpersonationStartIn — body of POST /platform/impersonations (02b API)
ImpersonationOut     — response shape for GET endpoints (02b API)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ImpersonationStartIn(BaseModel):
    tenant_id: uuid.UUID
    reason: str = Field(min_length=10, max_length=500)


class MintTenantTokenOut(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int  # seconds (access TTL)
    tenant_slug: str
    impersonation_id: uuid.UUID
    impersonation_expires_at: datetime


class ImpersonationOut(BaseModel):
    id: uuid.UUID
    platform_user_id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_user_id: uuid.UUID | None
    reason: str
    approval_request_id: uuid.UUID | None
    started_at: datetime
    expires_at: datetime
    ended_at: datetime | None
    ended_by: uuid.UUID | None
    revoked_at: datetime | None
    revoked_by: uuid.UUID | None

    model_config = {"from_attributes": True}
