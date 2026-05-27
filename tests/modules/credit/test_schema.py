"""Smoke tests for credit module SQLAlchemy models.

These tests verify the schema layer only — no service logic.
"""
from __future__ import annotations

from app.modules.credit.models import (
    Loan,
    LoanApplication,
    LoanInstallment,
    LoanProduct,
    LoanRepayment,
)


def test_credit_models_import() -> None:
    """All credit module models are importable without errors."""
    # If this test runs, the imports above succeeded.
    assert LoanProduct.__tablename__ == "loan_products"
    assert LoanApplication.__tablename__ == "loan_applications"
    assert Loan.__tablename__ == "loans"
    assert LoanInstallment.__tablename__ == "loan_installments"
    assert LoanRepayment.__tablename__ == "loan_repayments"


def test_loan_product_column_names() -> None:
    """LoanProduct has the expected columns (spot check)."""
    columns = {c.key for c in LoanProduct.__table__.columns}
    required = {
        "id", "name", "interest_method", "annual_interest_rate",
        "repayment_frequency", "max_term_periods", "min_amount", "max_amount",
        "required_approvals", "disbursement_destinations", "repayment_allocation",
        "gl_principal_receivable_code", "gl_interest_receivable_code",
        "gl_interest_income_code", "write_off_threshold", "is_active",
        "created_at", "updated_at",
    }
    assert required.issubset(columns), f"Missing columns: {required - columns}"


def test_loan_installment_has_no_audit_mixin() -> None:
    """LoanInstallment is NOT an AuditableMixin subclass (append-only table)."""
    from app.core.audit.mixin import AuditableMixin
    assert not issubclass(LoanInstallment, AuditableMixin)


def test_loan_repayment_has_no_updated_at() -> None:
    """LoanRepayment is append-only — no updated_at column."""
    columns = {c.key for c in LoanRepayment.__table__.columns}
    assert "updated_at" not in columns
