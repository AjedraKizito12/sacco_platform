from __future__ import annotations

import uuid
from typing import Any


def doc_id(schema: str | None, record_id: uuid.UUID) -> str:
    return f"{schema}:{record_id}" if schema else str(record_id)


def tenant_document(row: Any) -> dict[str, Any]:
    return {
        "entity_type": "tenant",
        "record_id": str(row.id),
        "title": row.name,
        "subtitle": row.slug,
        "url": f"/platform/tenants/{row.id}",
        "name": row.name,
        "slug": row.slug,
        "schema_name": row.schema_name,
        "status": row.status,
        "status_entity": "tenant",
    }


def member_document(schema: str, row: Any) -> dict[str, Any]:
    return {
        "entity_type": "member",
        "record_id": str(row.id),
        "tenant_schema": schema,
        "title": row.full_name,
        "subtitle": row.member_number,
        "url": f"/members/{row.id}",
        "full_name": row.full_name,
        "member_number": row.member_number,
        "email": getattr(row, "email", None),
        "phone": getattr(row, "phone", None),
        "status": row.status,
        "status_entity": "member",
    }


def loan_document(schema: str, row: Any) -> dict[str, Any]:
    return {
        "entity_type": "loan",
        "record_id": str(row.id),
        "tenant_schema": schema,
        "title": row.loan_reference,
        "subtitle": row.status,
        "url": f"/credit/loans/{row.id}",
        "loan_reference": row.loan_reference,
        "status": row.status,
        "status_entity": "loan",
    }


def loan_application_document(schema: str, row: Any) -> dict[str, Any]:
    return {
        "entity_type": "loan_application",
        "record_id": str(row.id),
        "tenant_schema": schema,
        "title": f"Application {str(row.id)[:8]}",
        "subtitle": row.status,
        "url": f"/credit/applications/{row.id}",
        "status": row.status,
        "status_entity": "loan_application",
    }


def savings_account_document(schema: str, row: Any) -> dict[str, Any]:
    # SavingsAccount has no status/account_number column (app/modules/savings/models.py) —
    # status is left empty (the display palette only renders a badge when non-empty) and
    # the title falls back to a short id.
    return {
        "entity_type": "savings_account",
        "record_id": str(row.id),
        "tenant_schema": schema,
        "title": f"Account {str(row.id)[:8]}",
        "subtitle": "",
        "url": f"/savings/accounts/{row.id}",
        "status": "",
        "status_entity": "savings_account",
    }


def invoice_document(row: Any) -> dict[str, Any]:
    return {
        "entity_type": "invoice",
        "record_id": str(row.id),
        "title": row.invoice_number,
        "subtitle": row.status,
        "url": f"/platform/billing/invoices/{row.id}",
        "invoice_number": row.invoice_number,
        "status": row.status,
        "status_entity": "invoice",
    }


def subscription_document(row: Any) -> dict[str, Any]:
    return {
        "entity_type": "subscription",
        "record_id": str(row.id),
        "title": f"Subscription {str(row.id)[:8]}",
        "subtitle": row.status,
        "url": f"/platform/billing/subscriptions/{row.id}",
        "status": row.status,
        "status_entity": "subscription",
    }


def platform_user_document(row: Any) -> dict[str, Any]:
    # PlatformUser has no status string column, only is_active (bool) — derived here.
    status = "active" if row.is_active else "inactive"
    return {
        "entity_type": "platform_user",
        "record_id": str(row.id),
        "title": row.full_name,
        "subtitle": row.email,
        "url": f"/platform/users/{row.id}",
        "full_name": row.full_name,
        "email": row.email,
        "status": status,
        "status_entity": "platform_user",
    }
