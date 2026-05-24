"""Pydantic schemas for tenant user API responses."""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, EmailStr

if TYPE_CHECKING:
    import uuid
    from datetime import datetime


class CreateTenantUserRequest(BaseModel):
    email: EmailStr
    full_name: str
    is_admin: bool = False


class UpdateTenantUserRequest(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None
    is_admin: bool | None = None


class TenantUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}
