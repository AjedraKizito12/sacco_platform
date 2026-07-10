"""No-op providers — v1 default. Nothing leaves the system."""
from __future__ import annotations

from app.core.notifications.providers.base import EmailProvider, SMSProvider


class NullEmailProvider(EmailProvider):
    name = "null"

    async def send(
        self, *, to: str, subject: str, text: str, html: str | None
    ) -> str | None:
        return None


class NullSMSProvider(SMSProvider):
    name = "null"

    async def send(self, *, to: str, body: str) -> str | None:
        return None
