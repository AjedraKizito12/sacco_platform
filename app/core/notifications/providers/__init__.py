"""Provider selection via settings. 'null' is the v1 default everywhere."""
from __future__ import annotations

from app.core.config import get_settings
from app.core.notifications.providers.base import EmailProvider, SMSProvider
from app.core.notifications.providers.log import LogEmailProvider, LogSMSProvider
from app.core.notifications.providers.null import NullEmailProvider, NullSMSProvider

_EMAIL: dict[str, type[EmailProvider]] = {"null": NullEmailProvider, "log": LogEmailProvider}
_SMS: dict[str, type[SMSProvider]] = {"null": NullSMSProvider, "log": LogSMSProvider}


def get_email_provider() -> EmailProvider:
    name = get_settings().notify_email_provider
    try:
        return _EMAIL[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown email provider '{name}'") from exc


def get_sms_provider() -> SMSProvider:
    name = get_settings().notify_sms_provider
    try:
        return _SMS[name]()
    except KeyError as exc:
        raise ValueError(f"Unknown SMS provider '{name}'") from exc
