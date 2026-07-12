from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.core.search.documents import doc_id, member_document, tenant_document


def test_tenant_document_shape():
    tid = uuid.uuid4()
    row = SimpleNamespace(id=tid, name="Demo SACCO", slug="demo-sacco", schema_name="tenant_demo_sacco")
    doc = tenant_document(row)
    assert doc["entity_type"] == "tenant"
    assert doc["record_id"] == str(tid)
    assert doc["title"] == "Demo SACCO"
    assert doc["subtitle"] == "demo-sacco"
    assert doc["url"] == f"/platform/tenants/{tid}"
    assert "tenant_schema" not in doc  # platform entity


def test_member_document_shape_and_scope():
    mid = uuid.uuid4()
    row = SimpleNamespace(
        id=mid, full_name="Grace N", member_number="M-0001",
        email="grace@example.com", phone="0700000000",
    )
    doc = member_document("tenant_demo_sacco", row)
    assert doc["entity_type"] == "member"
    assert doc["tenant_schema"] == "tenant_demo_sacco"
    assert doc["title"] == "Grace N"
    assert doc["subtitle"] == "M-0001"
    assert doc["url"] == f"/members/{mid}"
    # searchable fields present
    assert doc["member_number"] == "M-0001"
    assert doc["email"] == "grace@example.com"


def test_doc_id_forms():
    u = uuid.uuid4()
    assert doc_id("tenant_x", u) == f"tenant_x:{u}"
    assert doc_id(None, u) == str(u)
