"""Tests for the PaymentProcessor abstraction and concrete implementations."""
from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from app.platform_.billing.processors.base import PaymentProcessor, ProcessorResult
from app.platform_.billing.processors.flutterwave import FlutterwaveProcessor
from app.platform_.billing.processors.momo import MobileMoneyProcessor
from app.platform_.billing.processors.offline import OfflineProcessor
from app.platform_.billing.processors.stripe import StripeProcessor


def test_processor_is_abstract() -> None:
    with pytest.raises(TypeError):
        PaymentProcessor()  # type: ignore[abstract]


def test_processor_result_validates_status() -> None:
    ProcessorResult(status="pending", external_id=None, message="ok")
    ProcessorResult(status="succeeded", external_id="x", message="ok")
    ProcessorResult(status="failed", external_id=None, message="declined")
    with pytest.raises(ValueError, match="invalid ProcessorResult.status"):
        ProcessorResult(status="bogus", external_id=None, message="")


def test_processor_result_is_frozen() -> None:
    r = ProcessorResult(status="pending", external_id=None, message="x")
    with pytest.raises(FrozenInstanceError):
        r.status = "succeeded"  # type: ignore[misc]


def test_offline_processor_code() -> None:
    assert OfflineProcessor().code == "offline"


@pytest.mark.anyio
async def test_offline_initiate_returns_pending() -> None:
    p = OfflineProcessor()
    result = await p.initiate(
        invoice_id=uuid.uuid4(),
        amount=Decimal("50000"),
        payment_method="bank_transfer",
        external_reference="TXN-001",
    )
    assert result.status == "pending"
    assert result.external_id is None
    assert "awaiting" in result.message.lower()


@pytest.mark.anyio
async def test_offline_initiate_rejects_zero_amount() -> None:
    p = OfflineProcessor()
    result = await p.initiate(
        invoice_id=uuid.uuid4(),
        amount=Decimal("0"),
        payment_method="cash",
        external_reference=None,
    )
    assert result.status == "failed"
    assert "amount" in result.message.lower()


@pytest.mark.anyio
async def test_offline_initiate_rejects_negative_amount() -> None:
    p = OfflineProcessor()
    result = await p.initiate(
        invoice_id=uuid.uuid4(),
        amount=Decimal("-1"),
        payment_method="cash",
        external_reference=None,
    )
    assert result.status == "failed"


@pytest.mark.parametrize(
    ("cls", "code"),
    [
        (FlutterwaveProcessor, "flutterwave"),
        (StripeProcessor, "stripe"),
        (MobileMoneyProcessor, "momo"),
    ],
)
def test_stub_processors_raise_on_instantiation(cls, code) -> None:
    with pytest.raises(NotImplementedError, match=cls.__name__):
        cls()
