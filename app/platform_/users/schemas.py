import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class CreatePlatformUserRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=200)
    is_superuser: bool = False


class UpdatePlatformUserRequest(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=200)
    is_active: bool | None = None
    is_superuser: bool | None = None


class PlatformUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}
