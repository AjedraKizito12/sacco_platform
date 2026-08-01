"""Celery beat task: emit business-metric OTel gauges.

emit_business_metrics_gauges  — 60s: compute + push sacco_* business gauges
                                 (tenants, subscriptions, MRR, invoices,
                                 backup age, outbox depth, loans) via
                                 app.core.observability.metrics.record_business_gauges.
"""
from __future__ import annotations

import asyncio

import structlog

from app.workers.celery_app import celery_app

_log = structlog.get_logger(__name__)


@celery_app.task(name="app.core.observability.beat.emit_business_metrics_gauges")  # type: ignore[misc]
def emit_business_metrics_gauges() -> None:
    """Every 60s: compute and push business-metric gauges to Logfire."""
    from app.core.observability.metrics import record_business_gauges

    asyncio.run(record_business_gauges())
