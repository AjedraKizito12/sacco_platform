# app/modules/credit/services/payroll.py
"""PayrollBatchService — CSV/JSON batch submission, preview, and application."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select, text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.credit.models import Loan, PayrollBatch, PayrollBatchLine
from app.modules.maker_checker.service import ApprovalService

_log = structlog.get_logger(__name__)


class PayrollBatchService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def submit_batch(
        self,
        *,
        rows: list[dict[str, str]],
        source_format: str,
        actor_id: uuid.UUID,
        idempotency_key: str,
        clearing_account_id: uuid.UUID,
    ) -> PayrollBatch:
        """Validate rows, create batch + lines, submit for approval."""
        # Idempotency guard
        existing = await self._session.scalar(
            select(PayrollBatch).where(PayrollBatch.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing

        matched_rows, unmatched_rows, total_amount = await self._match_rows(rows)

        # Generate reference
        seq = await self._session.scalar(
            text("SELECT nextval('payroll_batch_number_seq')")
        )
        reference = f"PAY-{datetime.now(UTC).strftime('%Y%m')}-{seq:06d}"

        batch = PayrollBatch(
            reference=reference,
            status="pending_review",
            submitted_by=actor_id,
            total_rows=len(rows),
            matched_rows=len(matched_rows),
            unmatched_rows=len(unmatched_rows),
            total_amount=total_amount,
            source_format=source_format,
            idempotency_key=idempotency_key,
        )
        self._session.add(batch)
        await self._session.flush()

        for row in matched_rows + unmatched_rows:
            line = PayrollBatchLine(
                payroll_batch_id=batch.id,
                member_id=row.get("member_id"),
                raw_member_ref=row["raw_member_ref"],
                amount=Decimal(str(row["amount"])),
                loan_id=row.get("loan_id"),
                status=row["status"],
                error_reason=row.get("error_reason"),
            )
            self._session.add(line)

        await self._session.flush()

        # Submit for approval
        approval_svc = ApprovalService(self._session)
        request = await approval_svc.submit(
            operation_type="credit.apply_payroll_batch",
            payload={
                "batch_id": str(batch.id),
                "clearing_account_id": str(clearing_account_id),
            },
            requested_by=actor_id,
            required_approvals=1,
        )
        batch.approval_request_id = request.id
        await self._session.flush()

        _log.info(
            "credit.payroll_batch.submitted",
            batch_id=str(batch.id),
            matched=len(matched_rows),
            unmatched=len(unmatched_rows),
        )
        return batch

    async def submit_batch_csv(
        self,
        *,
        csv_bytes: bytes,
        actor_id: uuid.UUID,
        idempotency_key: str,
        clearing_account_id: uuid.UUID,
    ) -> PayrollBatch:
        """Parse CSV and delegate to submit_batch."""
        rows = self._parse_csv(csv_bytes)
        return await self.submit_batch(
            rows=rows,
            source_format="csv",
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            clearing_account_id=clearing_account_id,
        )

    def _parse_csv(self, csv_bytes: bytes) -> list[dict[str, str]]:
        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
        rows = []
        for row in reader:
            rows.append({
                "member_id": row.get("member_id", "").strip(),
                "amount": row.get("amount", "").strip(),
            })
        return rows

    async def _match_rows(
        self, rows: list[dict[str, str]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Decimal]:
        """For each row, find member + active loan. Returns (matched, unmatched, total)."""
        matched: list[dict[str, Any]] = []
        unmatched: list[dict[str, Any]] = []
        total = Decimal("0")

        for row in rows:
            raw_ref = str(row.get("member_id", "")).strip()
            amount_str = str(row.get("amount", "")).strip()

            try:
                amount = Decimal(amount_str)
                if amount <= 0:
                    raise ValueError("amount must be > 0")
            except Exception:
                unmatched.append({
                    "raw_member_ref": raw_ref,
                    "amount": amount_str or "0",
                    "status": "unmatched",
                    "error_reason": f"Invalid amount: {amount_str!r}",
                })
                continue

            # Try to find member by UUID
            member_id: uuid.UUID | None = None
            try:
                member_id = uuid.UUID(raw_ref)
            except ValueError:
                pass

            if member_id is None:
                unmatched.append({
                    "raw_member_ref": raw_ref,
                    "amount": str(amount),
                    "status": "unmatched",
                    "error_reason": "member_id is not a valid UUID",
                })
                continue

            # Find active loan for member
            loan = await self._session.scalar(
                select(Loan)
                .where(Loan.member_id == member_id)
                .where(Loan.status.in_(["disbursed", "in_arrears"]))
                .limit(1)
            )
            if loan is None:
                unmatched.append({
                    "raw_member_ref": raw_ref,
                    "member_id": member_id,
                    "amount": str(amount),
                    "status": "unmatched",
                    "error_reason": "no_active_loan",
                })
                continue

            matched.append({
                "raw_member_ref": raw_ref,
                "member_id": member_id,
                "amount": str(amount),
                "loan_id": loan.id,
                "status": "matched",
            })
            total += amount

        return matched, unmatched, total

    async def apply_batch(
        self,
        *,
        batch_id: uuid.UUID,
        actor_id: uuid.UUID,
        clearing_account_id: uuid.UUID | None = None,
    ) -> PayrollBatch:
        """Apply all matched lines. Each line committed independently."""
        batch = await self._session.scalar(
            select(PayrollBatch).where(PayrollBatch.id == batch_id).with_for_update()
        )
        if batch is None:
            raise ValueError(f"PayrollBatch '{batch_id}' not found")
        if batch.status != "approved":
            raise ValueError(f"Batch '{batch_id}' is not approved — status: {batch.status}")

        lines = (await self._session.execute(
            select(PayrollBatchLine)
            .where(PayrollBatchLine.payroll_batch_id == batch_id)
            .where(PayrollBatchLine.status == "matched")
        )).scalars().all()

        from app.modules.credit.services.repayment import LoanRepaymentService  # noqa: PLC0415

        for line in lines:
            idem_key = f"payroll-{batch_id}-{line.id}"
            try:
                repayment_svc = LoanRepaymentService(self._session)
                repayment = await repayment_svc.apply_repayment(
                    loan_id=line.loan_id,
                    amount=line.amount,
                    payment_account_id=clearing_account_id or uuid.UUID("00000000-0000-0000-0000-000000000001"),
                    posted_by=actor_id,
                    narration=f"Payroll deduction batch {batch.reference}",
                    idempotency_key=idem_key,
                )
                line.status = "applied"
                line.repayment_id = repayment.id
            except Exception as exc:
                line.status = "error"
                line.error_reason = str(exc)
                _log.warning(
                    "credit.payroll_batch.line_error",
                    batch_id=str(batch_id),
                    line_id=str(line.id),
                    error=str(exc),
                )
            await self._session.commit()

        # Re-fetch batch after per-line commits
        batch = await self._session.get(PayrollBatch, batch_id)
        batch.status = "applied"
        await self._session.flush()
        await self._session.commit()

        from app.core.outbox import EventPublisher  # noqa: PLC0415
        applied_count = sum(1 for ln in lines if ln.status == "applied")
        error_count = len(lines) - applied_count
        await EventPublisher.publish(
            self._session,
            aggregate_type="payroll_batch",
            aggregate_id=batch_id,
            event_type="PayrollBatchApplied",
            payload={
                "batch_id": str(batch_id),
                "applied_count": applied_count,
                "error_count": error_count,
                "total_amount": str(batch.total_amount),
            },
        )

        _log.info(
            "credit.payroll_batch.applied",
            batch_id=str(batch_id),
            applied=applied_count,
            errors=error_count,
        )
        return batch
