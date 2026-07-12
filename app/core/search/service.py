"""Query + indexing over Elasticsearch.

`build_query` is a pure DSL builder (unit-tested without ES). When a
`tenant_schema` is supplied the query ANDs a `term` filter pinning that schema
— the tenant-isolation guarantee for operator search. `search` short-circuits
on a blank query with no ES call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from elasticsearch.helpers import async_bulk

_FIELDS = [
    "title^3",
    "subtitle^2",
    "full_name",
    "member_number",
    "email",
    "phone",
    "name",
    "slug",
    "loan_reference",
    "invoice_number",
]


@dataclass
class SearchHit:
    entity_type: str
    id: str
    title: str
    subtitle: str
    url: str
    status: str = ""
    status_entity: str = ""


class SearchService:
    def __init__(self, client: Any) -> None:
        self._es = client

    @staticmethod
    def build_query(q: str, *, tenant_schema: str | None) -> dict[str, Any]:
        match: dict[str, Any] = {
            "multi_match": {
                "query": q,
                "type": "bool_prefix",
                "fields": _FIELDS,
            }
        }
        if tenant_schema is None:
            return {"query": match}
        return {
            "query": {
                "bool": {
                    "must": [match],
                    "filter": [{"term": {"tenant_schema": tenant_schema}}],
                }
            }
        }

    async def search(
        self,
        indices: list[str],
        q: str,
        *,
        tenant_schema: str | None = None,
        limit: int = 20,
    ) -> list[SearchHit]:
        if len(q.strip()) < 1 or not indices:
            return []
        body = self.build_query(q.strip(), tenant_schema=tenant_schema)
        body["size"] = limit
        # ignore_unavailable: an index that hasn't been created yet (before the
        # first reconcile beat runs) must yield no hits, not a 500.
        res = await self._es.search(
            index=",".join(indices), body=body, ignore_unavailable=True
        )
        hits: list[SearchHit] = []
        for h in res["hits"]["hits"]:
            src = h["_source"]
            hits.append(
                SearchHit(
                    entity_type=src["entity_type"],
                    id=src["record_id"],
                    title=src["title"],
                    subtitle=src.get("subtitle", ""),
                    url=src["url"],
                    status=src.get("status", ""),
                    status_entity=src.get("status_entity", ""),
                )
            )
        return hits

    async def bulk_index(
        self, index: str, docs: list[tuple[str, dict[str, Any]]]
    ) -> None:
        if not docs:
            return
        actions = [
            {"_index": index, "_id": did, "_source": src} for did, src in docs
        ]
        await async_bulk(self._es, actions)
