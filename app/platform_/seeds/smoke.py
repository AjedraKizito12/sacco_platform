"""Demo / smoke seed for manual testing of the reporting endpoints.

Inserts a small but cross-cutting data set into a tenant schema:

- 1 Member
- 1 SavingsProduct + 1 SavingsAccount + 3 SavingsTransactions
  (deposit 1000, deposit 500, withdrawal 200 — running balance ends at 1300)
- 1 LoanProduct + 1 LoanApplication + 1 Loan with snapshot balances
  (principal 50000, outstanding 40000, accrued_interest 500)
- 1 FeeAssessment (paid) + 1 FeeCollection (20000 UGX membership fee)
- 5 JournalEntries + 10 balanced JournalLines posted in January 2026

All rows use deterministic UUIDs (uuid5) keyed off the tenant schema name,
so the script is idempotent — re-running on the same schema produces no
duplicates.

Prerequisite: the standard tenant seeds must already have run
(`seed_defaults(engine, schema_name)` from `runner.py`). The smoke seed
resolves the seeded chart-of-accounts codes by `code` lookup.

Usage:
    python -m app.platform_.seeds.smoke <tenant_schema_name>
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_log = structlog.get_logger(__name__)
_SYSTEM = uuid.UUID("00000000-0000-0000-0000-000000000000")
_NS = uuid.UUID("a4c1f9b8-e7a3-4e92-9a4a-cc11d3e1f200")  # namespace for deterministic IDs


def _id(schema_name: str, label: str) -> str:
    """Deterministic UUID per (schema, label) so re-runs are idempotent."""
    return str(uuid.uuid5(_NS, f"{schema_name}:{label}"))


async def seed_smoke_data(engine: AsyncEngine, schema_name: str) -> None:
    """Insert demo data into *schema_name* for manual reporting tests."""
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        await session.execute(
            text(f"SET LOCAL search_path TO {schema_name}, platform")  # noqa: S608
        )
        await _seed(session, schema_name)
    _log.info("smoke.seeded", schema=schema_name)


async def _seed(session: AsyncSession, schema: str) -> None:
    coa = await _resolve_coa(session)
    fee_types = await _resolve_fee_types(session)

    member_id = _id(schema, "member")
    sp_id = _id(schema, "savings_product")
    sa_id = _id(schema, "savings_account")
    lp_id = _id(schema, "loan_product")
    la_id = _id(schema, "loan_application")
    loan_id = _id(schema, "loan")

    await _seed_member(session, member_id)
    await _seed_savings(session, schema, member_id, sp_id, sa_id, coa)
    await _seed_loan(session, schema, member_id, lp_id, la_id, loan_id, coa)
    await _seed_fees(session, schema, member_id, fee_types, coa)


async def _resolve_coa(session: AsyncSession) -> dict[str, str]:
    """Return {code: id} for the GL codes the smoke seed touches."""
    needed = {"1000", "1100", "1200", "1300", "2000", "4000", "4100"}
    rows = (
        await session.execute(
            text(
                "SELECT code, id::text FROM chart_of_accounts "
                "WHERE code IN ('1000','1100','1200','1300','2000','4000','4100')"
            )
        )
    ).all()
    found = {code: id_ for code, id_ in rows}
    missing = needed - found.keys()
    if missing:
        raise RuntimeError(
            f"Smoke seed requires COA codes {sorted(missing)} — run seed_defaults() first."
        )
    return found


async def _resolve_fee_types(session: AsyncSession) -> dict[str, str]:
    rows = (
        await session.execute(text("SELECT code, id::text FROM fee_types"))
    ).all()
    return {code: id_ for code, id_ in rows}


async def _seed_member(session: AsyncSession, member_id: str) -> None:
    await session.execute(
        text(
            "INSERT INTO members "
            "(id, member_number, full_name, date_of_birth, gender, status, joined_at, "
            "created_at, updated_at) "
            "VALUES (CAST(:id AS uuid), 'M-DEMO-001', 'Demo Member', "
            "'1990-01-15', 'male', 'active', '2026-01-01', now(), now()) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": member_id},
    )


async def _seed_savings(
    session: AsyncSession,
    schema: str,
    member_id: str,
    sp_id: str,
    sa_id: str,
    coa: dict[str, str],
) -> None:
    # Savings product (uses '2000 Member Savings' as the liability account)
    await session.execute(
        text(
            "INSERT INTO savings_products "
            "(id, name, interest_rate, minimum_balance, liability_account_id, "
            "is_active, created_at, updated_at) "
            "VALUES (CAST(:id AS uuid), 'Demo Savings', 5.0000, 0, "
            "CAST(:liab AS uuid), true, now(), now()) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": sp_id, "liab": coa["2000"]},
    )
    # Savings account
    await session.execute(
        text(
            "INSERT INTO savings_accounts "
            "(id, member_id, savings_product_id, product_name, interest_rate, "
            "minimum_balance, liability_account_id, created_at, updated_at) "
            "VALUES (CAST(:id AS uuid), CAST(:mid AS uuid), CAST(:spid AS uuid), "
            "'Demo Savings', 5.0000, 0, CAST(:liab AS uuid), now(), now()) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": sa_id, "mid": member_id, "spid": sp_id, "liab": coa["2000"]},
    )
    # Three transactions: deposit, deposit, withdrawal
    txns = [
        ("deposit", Decimal("1000"), date(2026, 1, 10), "Opening deposit"),
        ("deposit", Decimal("500"), date(2026, 1, 15), "Top-up deposit"),
        ("withdrawal", Decimal("200"), date(2026, 1, 20), "ATM withdrawal"),
    ]
    for i, (ttype, amount, when, narration) in enumerate(txns, start=1):
        je_id = _id(schema, f"je_sav_{i}")
        tx_id = _id(schema, f"sav_txn_{i}")
        line_dr_id = _id(schema, f"jl_sav_{i}_dr")
        line_cr_id = _id(schema, f"jl_sav_{i}_cr")
        posted_at = datetime(when.year, when.month, when.day, 10, 0, tzinfo=UTC)
        # Deposit: dr cash (1000), cr savings liability (2000)
        # Withdrawal: dr savings liability (2000), cr cash (1000)
        dr_acct = coa["1000"] if ttype == "deposit" else coa["2000"]
        cr_acct = coa["2000"] if ttype == "deposit" else coa["1000"]
        await _insert_journal_entry(
            session,
            je_id=je_id,
            reference=f"DEMO-SAV-{i:03d}",
            description=narration,
            posted_at=posted_at,
        )
        await _insert_journal_line(session, line_dr_id, je_id, dr_acct, amount, Decimal("0"))
        await _insert_journal_line(session, line_cr_id, je_id, cr_acct, Decimal("0"), amount)
        await session.execute(
            text(
                "INSERT INTO savings_transactions "
                "(id, savings_account_id, transaction_type, amount, narration, "
                "journal_entry_id, posted_by, posted_at, idempotency_key) "
                "VALUES (CAST(:id AS uuid), CAST(:sa AS uuid), :ttype, :amt, :narr, "
                "CAST(:je AS uuid), CAST(:by AS uuid), :at, :idem) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {
                "id": tx_id,
                "sa": sa_id,
                "ttype": ttype,
                "amt": amount,
                "narr": narration,
                "je": je_id,
                "by": str(_SYSTEM),
                "at": posted_at,
                "idem": _id(schema, f"sav_txn_idem_{i}"),
            },
        )


async def _seed_loan(
    session: AsyncSession,
    schema: str,
    member_id: str,
    lp_id: str,
    la_id: str,
    loan_id: str,
    coa: dict[str, str],
) -> None:
    # Loan product (Reducing balance, monthly, 12% APR, 12 periods)
    await session.execute(
        text(
            "INSERT INTO loan_products "
            "(id, name, interest_method, annual_interest_rate, repayment_frequency, "
            "max_term_periods, min_amount, max_amount, required_approvals, "
            "disbursement_destinations, repayment_allocation, "
            "gl_principal_receivable_code, gl_interest_receivable_code, "
            "gl_interest_income_code, write_off_threshold, required_guarantors, "
            "is_active, created_at, updated_at) "
            "VALUES (CAST(:id AS uuid), 'Demo Loan', 'reducing_balance', 12.0000, "
            "'monthly', 12, 10000, 1000000, 1, ARRAY['member_savings'], "
            "'INTEREST_PRINCIPAL', '1100', '1300', '4000', 0, 0, true, now(), now()) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": lp_id},
    )
    # Loan application
    await session.execute(
        text(
            "INSERT INTO loan_applications "
            "(id, loan_product_id, member_id, requested_amount, requested_term_periods, "
            "disbursement_destination, status, idempotency_key, created_at, updated_at) "
            "VALUES (CAST(:id AS uuid), CAST(:lp AS uuid), CAST(:mid AS uuid), 50000, 12, "
            "'member_savings', 'disbursed', :idem, now(), now()) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": la_id,
            "lp": lp_id,
            "mid": member_id,
            "idem": _id(schema, "la_idem"),
        },
    )
    # Disbursement JE — dr 1100 loan receivable 50000 / cr 1000 cash 50000
    je_id = _id(schema, "je_loan_disb")
    disb_at = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
    await _insert_journal_entry(
        session,
        je_id=je_id,
        reference="DEMO-LOAN-DISB-001",
        description="Demo loan disbursement",
        posted_at=disb_at,
    )
    await _insert_journal_line(
        session, _id(schema, "jl_loan_disb_dr"), je_id, coa["1100"], Decimal("50000"), Decimal("0")
    )
    await _insert_journal_line(
        session, _id(schema, "jl_loan_disb_cr"), je_id, coa["1000"], Decimal("0"), Decimal("50000")
    )
    # Loan row with snapshot balances (member paid back 10000 principal,
    # 500 interest accrued, no penalties, no write-off)
    await session.execute(
        text(
            "INSERT INTO loans "
            "(id, loan_reference, loan_application_id, loan_product_id, member_id, "
            "status, principal_amount, interest_method, annual_interest_rate, "
            "repayment_frequency, term_periods, repayment_allocation, "
            "disbursement_destination, "
            "gl_principal_receivable_id, gl_interest_receivable_id, "
            "gl_interest_income_id, gl_disbursement_account_id, "
            "outstanding_principal, accrued_interest, accrued_penalties, "
            "total_paid_principal, total_paid_interest, total_paid_penalties, "
            "total_written_off, disbursed_at, maturity_date, disbursed_by, "
            "idempotency_key, created_at, updated_at) "
            "VALUES (CAST(:id AS uuid), 'LN-DEMO-001', CAST(:la AS uuid), "
            "CAST(:lp AS uuid), CAST(:mid AS uuid), 'disbursed', 50000, "
            "'reducing_balance', 12.0000, 'monthly', 12, 'INTEREST_PRINCIPAL', "
            "'member_savings', CAST(:prc AS uuid), CAST(:intr AS uuid), "
            "CAST(:ii AS uuid), CAST(:disb AS uuid), "
            "40000, 500, 0, 10000, 0, 0, 0, :disb_at, '2027-01-05', "
            "CAST(:by AS uuid), :idem, now(), now()) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": loan_id,
            "la": la_id,
            "lp": lp_id,
            "mid": member_id,
            "prc": coa["1100"],
            "intr": coa["1300"],
            "ii": coa["4000"],
            "disb": coa["1000"],
            "disb_at": disb_at,
            "by": str(_SYSTEM),
            "idem": _id(schema, "loan_idem"),
        },
    )


async def _seed_fees(
    session: AsyncSession,
    schema: str,
    member_id: str,
    fee_types: dict[str, str],
    coa: dict[str, str],
) -> None:
    if "MEMBERSHIP" not in fee_types:
        _log.warning("smoke.fee_types_missing", missing="MEMBERSHIP")
        return
    ft_id = fee_types["MEMBERSHIP"]

    # Assessment booking — dr 1200 Receivable 20000 / cr 4100 Income 20000
    assess_at = datetime(2026, 1, 10, 11, 0, tzinfo=UTC)
    je_assess = _id(schema, "je_fee_assess")
    await _insert_journal_entry(
        session,
        je_id=je_assess,
        reference="DEMO-FEE-ASSESS-001",
        description="Demo membership fee assessment",
        posted_at=assess_at,
    )
    await _insert_journal_line(
        session, _id(schema, "jl_fee_assess_dr"), je_assess, coa["1200"], Decimal("20000"), Decimal("0")
    )
    await _insert_journal_line(
        session, _id(schema, "jl_fee_assess_cr"), je_assess, coa["4100"], Decimal("0"), Decimal("20000")
    )
    fa_id = _id(schema, "fee_assessment")
    await session.execute(
        text(
            "INSERT INTO fee_assessments "
            "(id, fee_type_id, target_type, target_id, period_start, amount, "
            "currency, status, journal_entry_id, assessed_at, created_at, updated_at) "
            "VALUES (CAST(:id AS uuid), CAST(:ft AS uuid), 'member', "
            "CAST(:mid AS uuid), '2026-01-01', 20000, 'UGX', 'paid', "
            "CAST(:je AS uuid), :at, now(), now()) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": fa_id, "ft": ft_id, "mid": member_id, "je": je_assess, "at": assess_at},
    )

    # Collection — dr 2000 Savings 20000 / cr 1200 Receivable 20000
    collect_at = datetime(2026, 1, 12, 14, 0, tzinfo=UTC)
    je_collect = _id(schema, "je_fee_collect")
    await _insert_journal_entry(
        session,
        je_id=je_collect,
        reference="DEMO-FEE-COLLECT-001",
        description="Demo membership fee collection",
        posted_at=collect_at,
    )
    await _insert_journal_line(
        session, _id(schema, "jl_fee_collect_dr"), je_collect, coa["2000"], Decimal("20000"), Decimal("0")
    )
    await _insert_journal_line(
        session, _id(schema, "jl_fee_collect_cr"), je_collect, coa["1200"], Decimal("0"), Decimal("20000")
    )
    fc_id = _id(schema, "fee_collection")
    await session.execute(
        text(
            "INSERT INTO fee_collections "
            "(id, fee_assessment_id, amount, method, collected_by, journal_entry_id, "
            "idempotency_key, source_module, source_id) "
            "VALUES (CAST(:id AS uuid), CAST(:fa AS uuid), 20000, 'savings_deduction', "
            "CAST(:by AS uuid), CAST(:je AS uuid), :idem, 'fees', CAST(:src AS uuid)) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": fc_id,
            "fa": fa_id,
            "by": str(_SYSTEM),
            "je": je_collect,
            "idem": _id(schema, "fc_idem"),
            "src": fa_id,
        },
    )


async def _insert_journal_entry(
    session: AsyncSession,
    *,
    je_id: str,
    reference: str,
    description: str,
    posted_at: datetime,
) -> None:
    await session.execute(
        text(
            "INSERT INTO journal_entries "
            "(id, reference, description, posted_by, posted_at, idempotency_key) "
            "VALUES (CAST(:id AS uuid), :ref, :desc, CAST(:by AS uuid), :at, :idem) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": je_id,
            "ref": reference,
            "desc": description,
            "by": str(_SYSTEM),
            "at": posted_at,
            "idem": je_id,  # use the deterministic id as idempotency_key — guaranteed unique per (schema, label)
        },
    )


async def _insert_journal_line(
    session: AsyncSession,
    line_id: str,
    je_id: str,
    account_id: str,
    debit: Decimal,
    credit: Decimal,
) -> None:
    await session.execute(
        text(
            "INSERT INTO journal_lines "
            "(id, journal_entry_id, account_id, debit_amount, credit_amount) "
            "VALUES (CAST(:id AS uuid), CAST(:je AS uuid), CAST(:acct AS uuid), :dr, :cr) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": line_id, "je": je_id, "acct": account_id, "dr": debit, "cr": credit},
    )


async def _main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m app.platform_.seeds.smoke <tenant_schema_name>")
        raise SystemExit(2)
    schema = sys.argv[1]
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        await seed_smoke_data(engine, schema)
    finally:
        await engine.dispose()
    print(f"smoke seed complete for schema={schema}")


if __name__ == "__main__":
    asyncio.run(_main())
