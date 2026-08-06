import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, EmailStr, Field, field_validator

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
    # Phase 7 — offboarding lifecycle + archival telemetry.
    lifecycle_state: str
    cancelled_at: datetime | None
    read_only_at: datetime | None
    archived_at: datetime | None
    hard_deleted_at: datetime | None
    retention_hold_until: datetime | None
    archive_storage_key: str | None
    archive_size_bytes: int | None
    archive_checksum: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TenantCreateResponse(BaseModel):
    tenant: TenantOut
    status_url: str


class TenantPatchIn(BaseModel):
    """Body of PATCH /platform/tenants/{id}. Currently only name is editable."""

    name: str = Field(min_length=1, max_length=200)


class TenantSuspendIn(BaseModel):
    """Body of POST /platform/tenants/{id}/suspend."""

    reason: str = Field(min_length=10, max_length=500)


class AssignPlanIn(BaseModel):
    """Body of POST /platform/tenants/{id}/assign-plan."""

    plan_id: uuid.UUID
    start_date: datetime | None = None


class TenantCancelIn(BaseModel):
    """Body of POST /platform/tenants/{id}/cancel (offboarding)."""

    reason: str = Field(min_length=10, max_length=500)


class ExtendRetentionIn(BaseModel):
    """Body of POST /platform/tenants/{id}/extend-retention."""

    hold_until: datetime


class TenantLifecycleEventOut(BaseModel):
    """One row of the tenant offboarding timeline."""

    id: uuid.UUID
    from_state: str
    to_state: str
    occurred_at: datetime
    reason: str | None
    actor_id: uuid.UUID | None
    metadata: dict[str, Any] = Field(
        validation_alias=AliasChoices("event_metadata", "metadata")
    )

    model_config = {"from_attributes": True, "populate_by_name": True}
