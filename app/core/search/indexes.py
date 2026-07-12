from __future__ import annotations

from typing import Any

from elasticsearch import AsyncElasticsearch

TENANTS_INDEX = "sacco_tenants"
MEMBERS_INDEX = "sacco_members"
LOANS_INDEX = "sacco_loans"
LOAN_APPLICATIONS_INDEX = "sacco_loan_applications"
SAVINGS_ACCOUNTS_INDEX = "sacco_savings_accounts"
INVOICES_INDEX = "sacco_invoices"
SUBSCRIPTIONS_INDEX = "sacco_subscriptions"
PLATFORM_USERS_INDEX = "sacco_platform_users"

_TEXT = {"type": "text", "fields": {"kw": {"type": "keyword"}}}

INDEX_MAPPINGS: dict[str, dict[str, Any]] = {
    TENANTS_INDEX: {
        "mappings": {"properties": {
            "entity_type": {"type": "keyword"},
            "record_id": {"type": "keyword"},
            "title": _TEXT, "subtitle": _TEXT, "url": {"type": "keyword", "index": False},
            "name": _TEXT, "slug": _TEXT, "schema_name": {"type": "keyword"},
            "status": {"type": "keyword"}, "status_entity": {"type": "keyword"},
        }}
    },
    MEMBERS_INDEX: {
        "mappings": {"properties": {
            "entity_type": {"type": "keyword"},
            "record_id": {"type": "keyword"},
            "tenant_schema": {"type": "keyword"},
            "title": _TEXT, "subtitle": _TEXT, "url": {"type": "keyword", "index": False},
            "full_name": _TEXT, "member_number": _TEXT, "email": _TEXT, "phone": _TEXT,
            "status": {"type": "keyword"}, "status_entity": {"type": "keyword"},
        }}
    },
    LOANS_INDEX: {
        "mappings": {"properties": {
            "entity_type": {"type": "keyword"},
            "record_id": {"type": "keyword"},
            "tenant_schema": {"type": "keyword"},
            "title": _TEXT, "subtitle": _TEXT, "url": {"type": "keyword", "index": False},
            "loan_reference": _TEXT,
            "status": {"type": "keyword"}, "status_entity": {"type": "keyword"},
        }}
    },
    LOAN_APPLICATIONS_INDEX: {
        "mappings": {"properties": {
            "entity_type": {"type": "keyword"},
            "record_id": {"type": "keyword"},
            "tenant_schema": {"type": "keyword"},
            "title": _TEXT, "subtitle": _TEXT, "url": {"type": "keyword", "index": False},
            "status": {"type": "keyword"}, "status_entity": {"type": "keyword"},
        }}
    },
    SAVINGS_ACCOUNTS_INDEX: {
        "mappings": {"properties": {
            "entity_type": {"type": "keyword"},
            "record_id": {"type": "keyword"},
            "tenant_schema": {"type": "keyword"},
            "title": _TEXT, "subtitle": _TEXT, "url": {"type": "keyword", "index": False},
            "status": {"type": "keyword"}, "status_entity": {"type": "keyword"},
        }}
    },
    INVOICES_INDEX: {
        "mappings": {"properties": {
            "entity_type": {"type": "keyword"},
            "record_id": {"type": "keyword"},
            "title": _TEXT, "subtitle": _TEXT, "url": {"type": "keyword", "index": False},
            "invoice_number": _TEXT,
            "status": {"type": "keyword"}, "status_entity": {"type": "keyword"},
        }}
    },
    SUBSCRIPTIONS_INDEX: {
        "mappings": {"properties": {
            "entity_type": {"type": "keyword"},
            "record_id": {"type": "keyword"},
            "title": _TEXT, "subtitle": _TEXT, "url": {"type": "keyword", "index": False},
            "status": {"type": "keyword"}, "status_entity": {"type": "keyword"},
        }}
    },
    PLATFORM_USERS_INDEX: {
        "mappings": {"properties": {
            "entity_type": {"type": "keyword"},
            "record_id": {"type": "keyword"},
            "title": _TEXT, "subtitle": _TEXT, "url": {"type": "keyword", "index": False},
            "full_name": _TEXT, "email": _TEXT,
            "status": {"type": "keyword"}, "status_entity": {"type": "keyword"},
        }}
    },
}


async def ensure_indices(client: AsyncElasticsearch) -> None:
    for name, body in INDEX_MAPPINGS.items():
        if not await client.indices.exists(index=name):
            await client.indices.create(index=name, body=body)
