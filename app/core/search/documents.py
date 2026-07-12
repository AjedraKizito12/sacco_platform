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
    }
