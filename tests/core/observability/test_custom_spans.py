"""Handle-smoke tests for the Task 9 custom metric counters/histograms/gauges.

These assert each new handle exists on `app.core.observability.metrics` and
that calling its increment/record/set method with a representative label
set does not raise. Deeper behavioural counter assertions would require an
OTel metric reader and are out of scope — see the Task 9 brief.
"""
from __future__ import annotations

from app.core.observability import metrics


def test_auth_login_attempts_handle_exists_and_increments() -> None:
    assert hasattr(metrics, "auth_login_attempts")
    metrics.auth_login_attempts.add(1, {"outcome": "success", "actor_type": "tenant_user"})
    metrics.auth_login_attempts.add(
        1, {"outcome": "invalid_credentials", "actor_type": "platform_user"}
    )
    metrics.auth_login_attempts.add(1, {"outcome": "locked", "actor_type": "member"})


def test_outbox_publish_duration_handle_exists_and_records() -> None:
    assert hasattr(metrics, "outbox_publish_duration")
    metrics.outbox_publish_duration.record(0.042)


def test_outbox_dead_lettered_handle_exists_and_increments() -> None:
    assert hasattr(metrics, "outbox_dead_lettered")
    metrics.outbox_dead_lettered.add(1)


def test_report_materialize_duration_handle_exists_and_records() -> None:
    assert hasattr(metrics, "report_materialize_duration")
    metrics.report_materialize_duration.record(1.23, {"report_type": "trial_balance"})


def test_report_last_run_handle_exists_and_sets() -> None:
    assert hasattr(metrics, "report_last_run")
    metrics.report_last_run.set(1_700_000_000.0, {"report_type": "loan_portfolio"})


def test_maker_checker_decisions_handle_exists_and_increments() -> None:
    assert hasattr(metrics, "maker_checker_decisions")
    metrics.maker_checker_decisions.add(1, {"outcome": "approved"})
    metrics.maker_checker_decisions.add(1, {"outcome": "rejected"})


def test_maker_checker_self_reject_handle_exists_and_increments() -> None:
    assert hasattr(metrics, "maker_checker_self_reject")
    metrics.maker_checker_self_reject.add(1)
