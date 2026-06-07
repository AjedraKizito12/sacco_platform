import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class CreatePlatformUserRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=200)
    role: str = Field(default="support", pattern="^(superuser|admin|finance|support)$")
    # Deprecated — kept for backward compat. If both are sent and conflict,
    # role wins. If only is_superuser=true is sent, role is coerced to 'superuser'.
    is_superuser: bool = False


class UpdatePlatformUserRequest(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=200)
    is_active: bool | None = None
    role: str | None = Field(
        default=None, pattern="^(superuser|admin|finance|support)$"
    )
    # Deprecated mirror — see CreatePlatformUserRequest.
    is_superuser: bool | None = None


class PlatformUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool
    role: str
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None

    model_config = {"from_attributes": True}
