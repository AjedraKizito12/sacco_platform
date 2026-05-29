# app/modules/reporting/services/fee_collection.py
"""FeeCollectionService — materialize and retrieve fee collection reports."""
from __future__ import annotations

import traceback
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import delete, func, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fees.models import FeeAssessment, FeeCollection, FeeType
from app.modules.reporting.models import ReportFeeCollectionRow, ReportRun

_log = structlog.get_logger(__name__)


class FeeCollectionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def materialize(self, *, period_start: date, period_end: date) -> ReportRun:
        """Aggregate fee_assessments + fee_collections per (fee_type, target_type).

        assessed_total  = SUM(assessment.amount) for assessments in period
        collected_total = SUM(collection.amount) for collections in period (via FK)
        outstanding_total = assessed_total - collected_total - waived_total
        waived_total    = SUM(assessment.amount) WHERE status = 'waived'
        as_of_date = period_end.
        """
        run = ReportRun(
            report_type="fee_collection",
            as_of_date=period_end,
            status="running",
            started_at=datetime.now(tz=UTC),
        )
        self._session.add(run)
        await self._session.flush()

        try:
            # Delete existing rows for this (period_start, period_end) across all prior runs
            # (idempotency: re-materializing the same period replaces the prior result).
            await self._session.execute(
                delete(ReportFeeCollectionRow).where(
                    ReportFeeCollectionRow.period_start == period_start,
                    ReportFeeCollectionRow.period_end == period_end,
                )
            )

            # Half-open interval [period_start 00:00 UTC, period_end+1d 00:00 UTC) — microsecond-safe.
            period_start_dt = datetime(period_start.year, period_start.month, period_start.day, tzinfo=UTC)
            period_end_dt = datetime(period_end.year, period_end.month, period_end.day, tzinfo=UTC) + timedelta(days=1)

            # Aggregate assessed totals per (fee_type, target_type) in the period.
            assessment_rows = (
                await self._session.execute(
                    select(
                        FeeType.id.label("fee_type_id"),
                        FeeType.name.label("fee_type_name"),
                        FeeAssessment.target_type,
                        func.coalesce(func.sum(FeeAssessment.amount), Decimal("0")).label("assessed_total"),
                    )
                    .join(FeeAssessment, FeeAssessment.fee_type_id == FeeType.id)
                    .where(
                        FeeAssessment.assessed_at >= period_start_dt,
                        FeeAssessment.assessed_at < period_end_dt,
                    )
                    .group_by(FeeType.id, FeeType.name, FeeAssessment.target_type)
                    .order_by(FeeType.name, FeeAssessment.target_type)
                )
            ).all()

            rows = []
            for ar in assessment_rows:
                # Sum collections for assessments of this fee_type+target_type in the period.
                collected_total = await self._session.scalar(
                    select(func.coalesce(func.sum(FeeCollection.amount), Decimal("0")))
                    .join(FeeAssessment, FeeCollection.fee_assessment_id == FeeAssessment.id)
                    .where(
                        FeeAssessment.fee_type_id == ar.fee_type_id,
                        FeeAssessment.target_type == ar.target_type,
                        FeeAssessment.assessed_at >= period_start_dt,
                        FeeAssessment.assessed_at < period_end_dt,
                    )
                ) or Decimal("0")

                waived_total = await self._session.scalar(
                    select(func.coalesce(func.sum(FeeAssessment.amount), Decimal("0")))
                    .where(
                        FeeAssessment.fee_type_id == ar.fee_type_id,
                        FeeAssessment.target_type == ar.target_type,
                        FeeAssessment.status == "waived",
                        FeeAssessment.assessed_at >= period_start_dt,
                        FeeAssessment.assessed_at < period_end_dt,
                    )
                ) or Decimal("0")

                outstanding_total = ar.assessed_total - collected_total - waived_total

                rows.append(
                    ReportFeeCollectionRow(
                        report_run_id=run.id,
                        period_start=period_start,
                        period_end=period_end,
                        fee_type_id=ar.fee_type_id,
                        fee_type_name=ar.fee_type_name,
                        target_type=ar.target_type,
                        assessed_total=ar.assessed_total,
                        collected_total=collected_total,
                        outstanding_total=outstanding_total,
                        waived_total=waived_total,
                    )
                )

            self._session.add_all(rows)

            run.status = "done"
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()

            _log.info(
                "reporting.fee_collection.materialized",
                period_start=str(period_start),
                period_end=str(period_end),
                rows=len(rows),
                run_id=str(run.id),
            )
            return run

        except Exception:
            run.status = "failed"
            run.error_detail = traceback.format_exc()
            run.completed_at = datetime.now(tz=UTC)
            await self._session.flush()
            raise

    async def get_fee_collection(
        self,
        *,
        period_end: date,
        fee_type_id: uuid.UUID | None = None,
    ) -> tuple[ReportRun | None, list[ReportFeeCollectionRow]]:
        """Return (run, rows) for the fee collection run where as_of_date == period_end."""
        run = await self._session.scalar(
            select(ReportRun)
            .where(
                ReportRun.report_type == "fee_collection",
                ReportRun.status == "done",
                ReportRun.as_of_date == period_end,
            )
            .order_by(ReportRun.as_of_date.desc())
            .limit(1)
        )
        if run is None:
            return None, []

        q = (
            select(ReportFeeCollectionRow)
            .where(ReportFeeCollectionRow.report_run_id == run.id)
            .order_by(ReportFeeCollectionRow.fee_type_name)
        )
        if fee_type_id is not None:
            q = q.where(ReportFeeCollectionRow.fee_type_id == fee_type_id)
        rows = list((await self._session.execute(q)).scalars().all())
        return run, rows
