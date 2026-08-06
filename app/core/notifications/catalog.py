"""Notification event taxonomy. Pure — no DB, no I/O.

Spec: docs/superpowers/specs/2026-07-10-notifications-framework-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass

CHANNELS: tuple[str, ...] = ("email", "sms", "in_app")
RECIPIENT_KINDS: tuple[str, ...] = ("platform_user", "tenant_user", "member")

_STAFF = ("platform_user", "tenant_user")
_ALL = RECIPIENT_KINDS
_EMAIL_IN_APP = ("email", "in_app")


@dataclass(frozen=True)
class NotificationEventSpec:
    code: str
    default_channels: tuple[str, ...]
    recipient_kinds: tuple[str, ...]


NOTIFICATION_CATALOG: tuple[NotificationEventSpec, ...] = (
    NotificationEventSpec("password_reset", _EMAIL_IN_APP, _ALL),
    NotificationEventSpec("maker_checker_pending", _EMAIL_IN_APP, _STAFF),
    NotificationEventSpec("maker_checker_approved", _EMAIL_IN_APP, _STAFF),
    NotificationEventSpec("maker_checker_rejected", _EMAIL_IN_APP, _STAFF),
    NotificationEventSpec("invoice_issued", _EMAIL_IN_APP, ("tenant_user",)),
    NotificationEventSpec("invoice_overdue", _EMAIL_IN_APP, ("tenant_user",)),
    NotificationEventSpec("subscription_suspended", _EMAIL_IN_APP, ("tenant_user",)),
    NotificationEventSpec("system_announcement", _EMAIL_IN_APP, _ALL),
    NotificationEventSpec("member_activated", _EMAIL_IN_APP, ("member",)),
    NotificationEventSpec("kyc_submission_approved", _EMAIL_IN_APP, ("member",)),
    NotificationEventSpec("kyc_submission_rejected", _EMAIL_IN_APP, ("member",)),
    NotificationEventSpec("loan_application_approved", _EMAIL_IN_APP, ("member",)),
    NotificationEventSpec("loan_application_rejected", _EMAIL_IN_APP, ("member",)),
    NotificationEventSpec("tenant_offboarding_cancelled", _EMAIL_IN_APP, ("tenant_user",)),
    NotificationEventSpec("tenant_offboarding_read_only", _EMAIL_IN_APP, ("tenant_user",)),
    NotificationEventSpec("tenant_offboarding_archived", _EMAIL_IN_APP, ("tenant_user",)),
    NotificationEventSpec("tenant_offboarding_restored", _EMAIL_IN_APP, ("tenant_user",)),
)

BY_CODE: dict[str, NotificationEventSpec] = {s.code: s for s in NOTIFICATION_CATALOG}


def spec_for(code: str) -> NotificationEventSpec:
    return BY_CODE[code]
