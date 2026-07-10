"""Default notification templates (locale 'en') for every catalog default channel.

The platform migration inserts these; tests (which create tables via
Base.metadata, not alembic) call seed_default_templates() directly.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notifications.catalog import NOTIFICATION_CATALOG
from app.core.notifications.models import NotificationTemplate

_TITLES: dict[str, str] = {
    "password_reset": "Password reset requested",
    "maker_checker_pending": "Approval needed: {{ operation_type }}",
    "maker_checker_approved": "Approved: {{ operation_type }}",
    "maker_checker_rejected": "Rejected: {{ operation_type }}",
    "invoice_issued": "Invoice {{ invoice_number }} issued",
    "invoice_overdue": "Invoice {{ invoice_number }} is overdue",
    "subscription_suspended": "Your subscription is suspended",
    "system_announcement": "{{ title }}",
    "member_activated": "Welcome — your membership is active",
    "kyc_submission_approved": "Your KYC details were approved",
    "kyc_submission_rejected": "Your KYC submission needs changes",
    "loan_application_approved": "Your loan application was approved",
    "loan_application_rejected": "Your loan application was declined",
}

_BODIES: dict[str, str] = {
    "password_reset": (
        "A password reset was requested for your account. "
        "If this wasn't you, contact support."
    ),
    "maker_checker_pending": (
        "{{ operation_type }} requested by {{ requested_by_label }} "
        "is waiting for approval."
    ),
    "maker_checker_approved": "Your {{ operation_type }} request was approved.",
    "maker_checker_rejected": "Your {{ operation_type }} request was rejected: {{ reason }}",
    "invoice_issued": (
        "Invoice {{ invoice_number }} for {{ amount }} {{ currency }} was issued. "
        "Due {{ due_date }}."
    ),
    "invoice_overdue": (
        "Invoice {{ invoice_number }} for {{ amount }} {{ currency }} is overdue. "
        "Please arrange payment."
    ),
    "subscription_suspended": (
        "Your SACCO's subscription is suspended. Contact the platform administrator."
    ),
    "system_announcement": "{{ body }}",
    "member_activated": "Hello {{ full_name }}, your membership {{ member_number }} is now active.",
    "kyc_submission_approved": (
        "Your submitted KYC details were reviewed and applied to your member record."
    ),
    "kyc_submission_rejected": (
        "Your KYC submission was rejected: {{ reason }}. Please review and resubmit."
    ),
    "loan_application_approved": "Your loan application for {{ amount }} was approved.",
    "loan_application_rejected": "Your loan application was declined: {{ reason }}",
}

_VARIABLES: dict[str, dict[str, str]] = {
    "password_reset": {},
    "maker_checker_pending": {
        "operation_type": "operation code",
        "requested_by_label": "maker display name",
    },
    "maker_checker_approved": {"operation_type": "operation code"},
    "maker_checker_rejected": {"operation_type": "operation code", "reason": "rejection reason"},
    "invoice_issued": {
        "invoice_number": "e.g. INV-2026-000001",
        "amount": "formatted amount",
        "currency": "ISO code",
        "due_date": "YYYY-MM-DD",
    },
    "invoice_overdue": {
        "invoice_number": "e.g. INV-2026-000001",
        "amount": "formatted amount",
        "currency": "ISO code",
    },
    "subscription_suspended": {},
    "system_announcement": {"title": "announcement title", "body": "announcement body"},
    "member_activated": {"full_name": "member name", "member_number": "member number"},
    "kyc_submission_approved": {},
    "kyc_submission_rejected": {"reason": "reviewer's reason"},
    "loan_application_approved": {"amount": "approved amount"},
    "loan_application_rejected": {"reason": "rejection reason"},
}


def _build() -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for spec in NOTIFICATION_CATALOG:
        for channel in spec.default_channels:
            rows.append(
                {
                    "code": spec.code,
                    "channel": channel,
                    "locale": "en",
                    "subject_template": _TITLES[spec.code],
                    "body_html": None,
                    "body_text": _BODIES[spec.code],
                    "sms_body": _BODIES[spec.code] if channel == "sms" else None,
                    "variables": _VARIABLES[spec.code],
                }
            )
    return tuple(rows)


DEFAULT_TEMPLATES: tuple[dict[str, Any], ...] = _build()


async def seed_default_templates(session: AsyncSession) -> int:
    """Insert any missing default templates. Idempotent; returns inserted count."""
    existing = {
        (code, channel, locale)
        for code, channel, locale in (
            await session.execute(
                select(
                    NotificationTemplate.code,
                    NotificationTemplate.channel,
                    NotificationTemplate.locale,
                )
            )
        ).all()
    }
    inserted = 0
    for row in DEFAULT_TEMPLATES:
        if (row["code"], row["channel"], row["locale"]) in existing:
            continue
        session.add(NotificationTemplate(**row))
        inserted += 1
    await session.flush()
    return inserted
