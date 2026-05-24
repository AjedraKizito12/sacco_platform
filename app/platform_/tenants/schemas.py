import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

_SLUG_RE = re.compile(r"^[a-z0-9-]{1,40}$")


class CreateTenantRequest(BaseModel):
    slug: str = Field(
        ...,
        description="URL-safe slug, lowercase letters/digits/hyphens, max 40 chars",
    )
    name: str = Field(..., min_length=1, max_length=200)
    admin_email: EmailStr | None = Field(
        None,
        description=(
            "If provided, seeds an initial admin user in the tenant. "
            "The user must set their password via the reset flow."
        ),
    )

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError("slug must match ^[a-z0-9-]{1,40}$")
        return v


class TenantOut(BaseModel):
    id: uuid.UUID
    slug: str
    schema_name: str
    name: str
    status: str
    is_active: bool
    provisioning_state: str | None
    failed_step: str | None
    failure_reason: str | None
    provisioning_started_at: datetime | None
    provisioning_completed_at: datetime | None
    seed_version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TenantCreateResponse(BaseModel):
    tenant: TenantOut
    status_url: str
