from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchEntity:
    entity_type: str
    index: str
    scope_kind: str  # "platform" | "tenant"
    table: str       # source table (unqualified for tenant, platform.-qualified for platform)
    timestamp_col: str
    status_entity: str


SEARCH_ENTITIES: list[SearchEntity] = [
    SearchEntity(
        "tenant",
        "sacco_tenants",
        "platform",
        "platform.tenants",
        "updated_at",
        "tenant",
    ),
    SearchEntity(
        "platform_user",
        "sacco_platform_users",
        "platform",
        "platform.platform_users",
        "updated_at",
        "platform_user",
    ),
    SearchEntity(
        "invoice",
        "sacco_invoices",
        "platform",
        "platform.invoices",
        "updated_at",
        "invoice",
    ),
    SearchEntity(
        "subscription",
        "sacco_subscriptions",
        "platform",
        "platform.subscriptions",
        "updated_at",
        "subscription",
    ),
    SearchEntity(
        "member",
        "sacco_members",
        "tenant",
        "members",
        "updated_at",
        "member",
    ),
    SearchEntity(
        "loan",
        "sacco_loans",
        "tenant",
        "loans",
        "updated_at",
        "loan",
    ),
    SearchEntity(
        "savings_account",
        "sacco_savings_accounts",
        "tenant",
        "savings_accounts",
        "updated_at",
        "savings_account",
    ),
    SearchEntity(
        "loan_application",
        "sacco_loan_applications",
        "tenant",
        "loan_applications",
        "updated_at",
        "loan_application",
    ),
]

_BY_TYPE = {e.entity_type: e for e in SEARCH_ENTITIES}


def platform_indices() -> list[str]:
    return [e.index for e in SEARCH_ENTITIES if e.scope_kind == "platform"]


def tenant_indices() -> list[str]:
    return [e.index for e in SEARCH_ENTITIES if e.scope_kind == "tenant"]


def resolve_indices(audience: str, types: str | None) -> list[str]:
    allowed = platform_indices() if audience == "platform" else tenant_indices()
    if not types:
        return allowed
    wanted = {t.strip() for t in types.split(",") if t.strip()}
    return [
        _BY_TYPE[t].index
        for t in wanted
        if t in _BY_TYPE and _BY_TYPE[t].index in allowed
    ]
