"""Tests for the PaymentProcessor abstraction and concrete implementations."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.platform_.billing.processors.base import PaymentProcessor, ProcessorResult


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
