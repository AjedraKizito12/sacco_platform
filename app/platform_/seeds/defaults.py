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
        "name": "Membership Fee",
        "description": "One-time fee paid on joining",
        "amount_minor_units": 5000_00,  # 5,000 UGX in minor units
        "currency": "UGX",
        "is_recurring": False,
    },
    {
        "code": "ANNUAL_SUBSCRIPTION",
        "name": "Annual Subscription",
        "description": "Annual renewal fee",
        "amount_minor_units": 2000_00,  # 2,000 UGX in minor units
        "currency": "UGX",
        "is_recurring": True,
        "recurrence_months": 12,
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
