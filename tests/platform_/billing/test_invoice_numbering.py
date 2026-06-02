"""InvoiceService numbering tests — the per-year sequence."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.platform_.billing.services.invoice_service import InvoiceService


async def _set_platform(s: AsyncSession) -> None:
    await s.execute(text("SET LOCAL search_path TO platform, public"))
    s.sync_session.info["is_platform"] = True


@pytest.fixture
async def factory(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.mark.anyio
async def test_invoice_number_format(factory) -> None:
    """Format is INV-YYYY-NNNNNN with zero-padded 6-digit counter."""
    async with factory() as s:
        await _set_platform(s)
        svc = InvoiceService(s)
        n = await svc._next_invoice_number(today=date(2026, 6, 1))
        assert n.startswith("INV-2026-")
        suffix = n.split("-")[-1]
        assert len(suffix) == 6
        assert suffix.isdigit()
        await s.commit()


@pytest.mark.anyio
async def test_invoice_number_is_monotonic_within_year(factory) -> None:
    async with factory() as s:
        await _set_platform(s)
        svc = InvoiceService(s)
        a = await svc._next_invoice_number(today=date(2026, 6, 1))
        b = await svc._next_invoice_number(today=date(2026, 6, 1))
        c = await svc._next_invoice_number(today=date(2026, 12, 31))
        await s.commit()
        assert int(a.split("-")[-1]) < int(b.split("-")[-1])
        assert int(b.split("-")[-1]) < int(c.split("-")[-1])


@pytest.mark.anyio
async def test_invoice_number_creates_sequence_for_new_year(factory) -> None:
    """The first invoice of a new year creates its sequence on demand."""
    async with factory() as s:
        await _set_platform(s)
        # Drop any stray 2099 sequence from a prior test run
        await s.execute(text("DROP SEQUENCE IF EXISTS platform.invoice_seq_2099"))
        svc = InvoiceService(s)
        n = await svc._next_invoice_number(today=date(2099, 1, 1))
        assert n == "INV-2099-000001"
        # Cleanup
        await s.execute(text("DROP SEQUENCE platform.invoice_seq_2099"))
        await s.commit()
