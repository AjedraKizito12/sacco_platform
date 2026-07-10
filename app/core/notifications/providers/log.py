"""Log providers — write a structlog line; useful in closed beta and tests."""
from __future__ import annotations

import uuid

import structlog

from app.core.notifications.providers.base import EmailProvider, SMSProvider

_log = structlog.get_logger(__name__)


class LogEmailProvider(EmailProvider):
    name = "log"

    async def send(
        self, *, to: str, subject: str, text: str, html: str | None
    ) -> str | None:
        external_id = f"log-{uuid.uuid4()}"
        _log.info("notification.email", to=to, subject=subject, external_id=external_id)
        return external_id


class LogSMSProvider(SMSProvider):
    name = "log"

    async def send(self, *, to: str, body: str) -> str | None:
        external_id = f"log-{uuid.uuid4()}"
        _log.info("notification.sms", to=to, external_id=external_id)
        return external_id
