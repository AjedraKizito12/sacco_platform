"""Pydantic schemas for the notifications HTTP APIs."""
from __future__ import annotations

import uuid  # noqa: TC003 (FastAPI runtime introspection)
from datetime import datetime  # noqa: TC003
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NotificationFeedItemOut(BaseModel):
    id: uuid.UUID
    event_code: str
    title: str
    body: str
    status: str
    created_at: datetime
    read_at: datetime | None


class NotificationPreferenceIn(BaseModel):
    event_code: str
    channel: str
    enabled: bool


class NotificationPreferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_code: str
    channel: str
    enabled: bool


class NotificationTemplateIn(BaseModel):
    code: str
    channel: str
    locale: str = "en"
    subject_template: str | None = None
    body_html: str | None = None
    body_text: str | None = None
    sms_body: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)


class NotificationTemplatePatch(BaseModel):
    subject_template: str | None = None
    body_html: str | None = None
    body_text: str | None = None
    sms_body: str | None = None
    variables: dict[str, Any] | None = None
    is_active: bool | None = None


class NotificationTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    channel: str
    locale: str
    subject_template: str | None
    body_html: str | None
    body_text: str | None
    sms_body: str | None
    variables: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class NotificationEventAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_code: str
    recipient_kind: str
    recipient_user_id: uuid.UUID
    recipient_email: str | None
    channels: list[str]
    context: dict[str, Any]
    scheduled_at: datetime
    status: str
    created_at: datetime
