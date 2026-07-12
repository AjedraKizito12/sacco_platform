from __future__ import annotations

import asyncio

from app.core.search.service import SearchService


def test_build_query_without_schema_has_no_filter():
    body = SearchService.build_query("grace", tenant_schema=None)
    assert "multi_match" in str(body)
    assert "term" not in str(body)  # no tenant filter


def test_build_query_with_schema_ands_tenant_filter():
    body = SearchService.build_query("grace", tenant_schema="tenant_demo_sacco")
    # the term filter pins the schema — tenant isolation
    filters = body["query"]["bool"]["filter"]
    assert {"term": {"tenant_schema": "tenant_demo_sacco"}} in filters


def test_blank_query_is_rejected_before_es():
    # search() must short-circuit on blank q; the object() client is never used.
    svc = SearchService(client=object())
    out = asyncio.run(svc.search(["sacco_members"], "   "))
    assert out == []
