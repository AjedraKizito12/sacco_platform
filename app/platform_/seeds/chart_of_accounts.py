"""Chart of accounts seed data for a standard SACCO.

These are inserted into the tenant's chart_of_accounts table (created by the
ledger module). Seed runner skips gracefully if the table doesn't exist yet.
"""
from __future__ import annotations

# Each entry: code, name, account_type, normal_balance ('debit'|'credit')
CHART_OF_ACCOUNTS: list[dict[str, str]] = [
    # Assets (normal balance: debit)
    {
        "code": "1000",
        "name": "Cash and Cash Equivalents",
        "account_type": "asset",
        "normal_balance": "debit",
    },
    {
        "code": "1100",
        "name": "Member Loans Receivable",
        "account_type": "asset",
        "normal_balance": "debit",
    },
    {
        "code": "1200",
        "name": "Share Capital Receivable",
        "account_type": "asset",
        "normal_balance": "debit",
    },
    {
        "code": "1300",
        "name": "Interest Receivable",
        "account_type": "asset",
        "normal_balance": "debit",
    },
    # Liabilities (normal balance: credit)
    {
        "code": "2000",
        "name": "Member Savings",
        "account_type": "liability",
        "normal_balance": "credit",
    },
    {
        "code": "2100",
        "name": "Fixed Deposits",
        "account_type": "liability",
        "normal_balance": "credit",
    },
    {
        "code": "2200",
        "name": "External Borrowings",
        "account_type": "liability",
        "normal_balance": "credit",
    },
    # Equity (normal balance: credit)
    {
        "code": "3000",
        "name": "Share Capital",
        "account_type": "equity",
        "normal_balance": "credit",
    },
    {
        "code": "3100",
        "name": "Retained Surplus",
        "account_type": "equity",
        "normal_balance": "credit",
    },
    {
        "code": "3200",
        "name": "Statutory Reserve",
        "account_type": "equity",
        "normal_balance": "credit",
    },
    # Income (normal balance: credit)
    {
        "code": "4000",
        "name": "Interest on Loans",
        "account_type": "income",
        "normal_balance": "credit",
    },
    {
        "code": "4100",
        "name": "Membership Fees",
        "account_type": "income",
        "normal_balance": "credit",
    },
    {
        "code": "4200",
        "name": "Annual Subscription Fees",
        "account_type": "income",
        "normal_balance": "credit",
    },
    {
        "code": "4300",
        "name": "Penalties and Charges",
        "account_type": "income",
        "normal_balance": "credit",
    },
    # Expenses (normal balance: debit)
    {
        "code": "5000",
        "name": "Operating Expenses",
        "account_type": "expense",
        "normal_balance": "debit",
    },
    {
        "code": "5100",
        "name": "Interest on Savings",
        "account_type": "expense",
        "normal_balance": "debit",
    },
    {
        "code": "5200",
        "name": "Loan Write-offs",
        "account_type": "expense",
        "normal_balance": "debit",
    },
]
