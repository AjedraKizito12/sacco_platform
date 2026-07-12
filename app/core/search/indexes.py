from __future__ import annotations

from typing import Any

from elasticsearch import AsyncElasticsearch

TENANTS_INDEX = "sacco_tenants"
MEMBERS_INDEX = "sacco_members"

_TEXT = {"type": "text", "fields": {"kw": {"type": "keyword"}}}

INDEX_MAPPINGS: dict[str, dict[str, Any]] = {
    TENANTS_INDEX: {
        "mappings": {"properties": {
            "entity_type": {"type": "keyword"},
            "record_id": {"type": "keyword"},
            "title": _TEXT, "subtitle": _TEXT, "url": {"type": "keyword", "index": False},
            "name": _TEXT, "slug": _TEXT, "schema_name": {"type": "keyword"},
        }}
    },
    MEMBERS_INDEX: {
        "mappings": {"properties": {
            "entity_type": {"type": "keyword"},
            "record_id": {"type": "keyword"},
            "tenant_schema": {"type": "keyword"},
            "title": _TEXT, "subtitle": _TEXT, "url": {"type": "keyword", "index": False},
            "full_name": _TEXT, "member_number": _TEXT, "email": _TEXT, "phone": _TEXT,
        }}
    },
}


async def ensure_indices(client: AsyncElasticsearch) -> None:
    for name, body in INDEX_MAPPINGS.items():
        if not await client.indices.exists(index=name):
            await client.indices.create(index=name, body=body)
