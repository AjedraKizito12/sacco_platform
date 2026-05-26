"""Default seed data for roles, fee types, and product templates.

Tables are created by their respective modules (iam, fees, savings/shares/credit).
The seed runner skips gracefully when tables don't exist yet.
"""
from __future__ import annotations

DEFAULT_ROLES: list[dict[str, str]] = [
    {"name": "admin", "description": "Full administrative access"},
    {"name": "manager", "description": "Branch/department manager"},
    {"name": "loan_officer", "description": "Process loan applications and disbursements"},
    {"name": "teller", "description": "Front-office cash and transaction handling"},
    {"name": "member_services", "description": "Member registration and KYC"},
    {"name": "auditor", "description": "Read-only audit and reporting access"},
]

DEFAULT_FEE_TYPES: list[dict[str, object]] = [
    {
        "code": "MEMBERSHIP",
        "name": "Membership Registration Fee",
        "description": "One-time fee charged when a member is activated",
        "applicable_to": "member",
        "amount_kind": "fixed",
        "amount": "20000.0000",  # 20,000 UGX — override per tenant via PATCH after provisioning
        "currency": "UGX",
        "trigger_kind": "event",
        "event_name": "MemberActivated",
        "schedule_config": None,
        "gl_income_account_code": "4100",  # Fee Income
        "gl_receivable_account_code": "1200",  # Fee Receivable
        "is_active": True,
        "requires_collection": True,
    },
    {
        "code": "ANNUAL_SUB",
        "name": "Annual Subscription Fee",
        "description": "Annual renewal fee for active members",
        "applicable_to": "member",
        "amount_kind": "fixed",
        "amount": "50000.0000",  # 50,000 UGX
        "currency": "UGX",
        "trigger_kind": "schedule",
        "event_name": None,
        "schedule_config": {"recurrence": "yearly", "month": 1, "day": 1},
        "gl_income_account_code": "4101",  # Annual Sub Income
        "gl_receivable_account_code": "1201",  # Annual Sub Receivable
        "is_active": True,
        "requires_collection": True,
    },
]

DEFAULT_PRODUCT_TEMPLATES: list[dict[str, object]] = [
    {
        "code": "SAVINGS_BASIC",
        "name": "Basic Savings Account",
        "product_type": "savings",
        "status": "draft",
        "interest_rate_pa": "0.06",  # 6% p.a.
        "currency": "UGX",
    },
    {
        "code": "SHARES_ORDINARY",
        "name": "Ordinary Shares",
        "product_type": "shares",
        "status": "draft",
        "nominal_value_minor_units": 1000_00,  # 1,000 UGX per share
        "currency": "UGX",
    },
    {
        "code": "LOAN_PERSONAL",
        "name": "Personal Loan",
        "product_type": "loan",
        "status": "draft",
        "interest_rate_pa": "0.18",  # 18% p.a.
        "currency": "UGX",
        "max_term_months": 36,
    },
]
