"""Provider interfaces. Return value = provider external id (or None); raise = failure."""
from __future__ import annotations

from abc import ABC, abstractmethod


class EmailProvider(ABC):
    name: str

    @abstractmethod
    async def send(
        self, *, to: str, subject: str, text: str, html: str | None
    ) -> str | None: ...


class SMSProvider(ABC):
    name: str

    @abstractmethod
    async def send(self, *, to: str, body: str) -> str | None: ...
