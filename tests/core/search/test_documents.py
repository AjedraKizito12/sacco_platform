from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.core.search.documents import (
    doc_id,
    invoice_document,
    loan_application_document,
    loan_document,
    member_document,
    platform_user_document,
    savings_account_document,
    subscription_document,
    tenant_document,
)


def test_tenant_document_shape():
    tid = uuid.uuid4()
    row = SimpleNamespace(
        id=tid, name="Demo SACCO", slug="demo-sacco", schema_name="tenant_demo_sacco", status="active",
    )
    doc = tenant_document(row)
    assert doc["entity_type"] == "tenant"
    assert doc["record_id"] == str(tid)
    assert doc["title"] == "Demo SACCO"
    assert doc["subtitle"] == "demo-sacco"
    assert doc["url"] == f"/platform/tenants/{tid}"
    assert "tenant_schema" not in doc  # platform entity
    assert doc["status"] == "active"
    assert doc["status_entity"] == "tenant"


def test_member_document_shape_and_scope():
    mid = uuid.uuid4()
    row = SimpleNamespace(
        id=mid, full_name="Grace N", member_number="M-0001",
        email="grace@example.com", phone="0700000000", status="active",
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
    assert doc["status"] == "active"
    assert doc["status_entity"] == "member"


def test_loan_document_shape():
    lid = uuid.uuid4()
    row = SimpleNamespace(id=lid, loan_reference="L-0001", member_id=uuid.uuid4(), status="disbursed")
    doc = loan_document("tenant_demo_sacco", row)
    assert doc["entity_type"] == "loan"
    assert doc["tenant_schema"] == "tenant_demo_sacco"
    assert doc["title"] == "L-0001"
    assert doc["subtitle"] == "disbursed"
    assert doc["url"] == f"/credit/loans/{lid}"
    assert doc["loan_reference"] == "L-0001"
    assert doc["status"] == "disbursed"
    assert doc["status_entity"] == "loan"


def test_loan_application_document_shape():
    aid = uuid.uuid4()
    row = SimpleNamespace(id=aid, member_id=uuid.uuid4(), status="submitted")
    doc = loan_application_document("tenant_demo_sacco", row)
    assert doc["entity_type"] == "loan_application"
    assert doc["tenant_schema"] == "tenant_demo_sacco"
    assert doc["title"] == f"Application {str(aid)[:8]}"
    assert doc["subtitle"] == "submitted"
    assert doc["url"] == f"/credit/applications/{aid}"
    assert doc["status"] == "submitted"
    assert doc["status_entity"] == "loan_application"


def test_savings_account_document_shape():
    sid = uuid.uuid4()
    row = SimpleNamespace(id=sid, member_id=uuid.uuid4())
    doc = savings_account_document("tenant_demo_sacco", row)
    assert doc["entity_type"] == "savings_account"
    assert doc["tenant_schema"] == "tenant_demo_sacco"
    assert doc["title"] == f"Account {str(sid)[:8]}"
    assert doc["url"] == f"/savings/accounts/{sid}"
    assert doc["status"] == ""
    assert doc["status_entity"] == "savings_account"


def test_invoice_document_shape():
    iid = uuid.uuid4()
    row = SimpleNamespace(id=iid, invoice_number="INV-2026-000001", tenant_id=uuid.uuid4(), status="issued")
    doc = invoice_document(row)
    assert doc["entity_type"] == "invoice"
    assert "tenant_schema" not in doc  # platform entity
    assert doc["title"] == "INV-2026-000001"
    assert doc["subtitle"] == "issued"
    assert doc["url"] == f"/platform/billing/invoices/{iid}"
    assert doc["invoice_number"] == "INV-2026-000001"
    assert doc["status"] == "issued"
    assert doc["status_entity"] == "invoice"


def test_subscription_document_shape():
    subid = uuid.uuid4()
    row = SimpleNamespace(id=subid, tenant_id=uuid.uuid4(), plan_id=uuid.uuid4(), status="active")
    doc = subscription_document(row)
    assert doc["entity_type"] == "subscription"
    assert "tenant_schema" not in doc  # platform entity
    assert doc["title"] == f"Subscription {str(subid)[:8]}"
    assert doc["subtitle"] == "active"
    assert doc["url"] == f"/platform/billing/subscriptions/{subid}"
    assert doc["status"] == "active"
    assert doc["status_entity"] == "subscription"


def test_platform_user_document_shape():
    uid = uuid.uuid4()
    row = SimpleNamespace(id=uid, full_name="Ada Admin", email="ada@example.com", is_active=True)
    doc = platform_user_document(row)
    assert doc["entity_type"] == "platform_user"
    assert "tenant_schema" not in doc  # platform entity
    assert doc["title"] == "Ada Admin"
    assert doc["subtitle"] == "ada@example.com"
    assert doc["url"] == f"/platform/users/{uid}"
    assert doc["full_name"] == "Ada Admin"
    assert doc["email"] == "ada@example.com"
    assert doc["status"] == "active"
    assert doc["status_entity"] == "platform_user"


def test_platform_user_document_inactive_status():
    row = SimpleNamespace(id=uuid.uuid4(), full_name="Ada Admin", email="ada@example.com", is_active=False)
    doc = platform_user_document(row)
    assert doc["status"] == "inactive"


def test_doc_id_forms():
    u = uuid.uuid4()
    assert doc_id("tenant_x", u) == f"tenant_x:{u}"
    assert doc_id(None, u) == str(u)
