"""Tenant dashboard read-model — aggregates member/savings/credit KPIs.

Read-only. Owns no tables; it composes the public service interfaces of the
members, savings, and credit modules (never their models) into a single
round-trip for the operator portal's tenant dashboard.
"""
