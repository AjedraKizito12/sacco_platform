"""Member KYC submissions: member submit path + operator review queue.

MemberSelfService is the member-facing write path (per the 2026-06-29 member
self-service spec, KYC submission is a member write). KycReviewService is the
operator review path — approve() is the ONLY code path that applies KYC fields
to the member row (members never write identity fields directly). Review is
single-reviewer, NOT maker-checker.

Field application uses plain ORM attribute writes so AuditableMixin records
the member-row diff (actor_type comes from the request's contextvars).
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kyc.catalog import MEMBER_KYC_CATALOG
from app.modules.members.models import KycSubmission, Member

# The non-locked catalog keys — exactly the kyc_submissions snapshot columns.
EDITABLE_KYC_FIELDS: tuple[str, ...] = tuple(
    f.key for f in MEMBER_KYC_CATALOG if not f.locked
)

# Editable fields with a UNIQUE constraint on members — checked at approve
# time only (submit never validates uniqueness, per the 2026-06-29 spec).
_UNIQUE_FIELDS: tuple[str, ...] = ("national_id_number", "email")

_log = structlog.get_logger(__name__)


class SubmissionNotFound(Exception):
    pass


class SubmissionNotPending(Exception):
    pass


class KycFieldConflict(Exception):
    """Approving would collide with another member's unique field value."""

    def __init__(self, field: str, value: str) -> None:
        self.field = field
        super().__init__(f"Another member already has {field} '{value}'")


class MemberSelfService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def latest_submission(self, member_id: uuid.UUID) -> KycSubmission | None:
        return (
            await self._session.execute(
                select(KycSubmission)
                .where(KycSubmission.member_id == member_id)
                .order_by(KycSubmission.submitted_at.desc(), KycSubmission.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def submit_kyc(
        self, member_id: uuid.UUID, values: Mapping[str, object | None]
    ) -> KycSubmission:
        """Create the member's pending submission, or supersede it in place.

        The snapshot is the FULL intended state of the editable fields: keys
        absent from ``values`` are stored as None (the portal form prefills
        current values, so a blank is an intentional clear). Uniqueness is
        deliberately not checked here — it surfaces at approve time.
        """
        pending = (
            await self._session.execute(
                select(KycSubmission).where(
                    KycSubmission.member_id == member_id,
                    KycSubmission.status == "pending",
                )
            )
        ).scalar_one_or_none()
        if pending is None:
            pending = KycSubmission(member_id=member_id)
            self._session.add(pending)
        for key in EDITABLE_KYC_FIELDS:
            setattr(pending, key, values.get(key))
        pending.submitted_at = datetime.now(UTC)
        await self._session.flush()
        _log.info("member.kyc_submitted", member_id=str(member_id), submission_id=str(pending.id))
        return pending


class KycReviewService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(
        self, status: str | None = None
    ) -> list[tuple[KycSubmission, Member]]:
        q = (
            select(KycSubmission, Member)
            .join(Member, KycSubmission.member_id == Member.id)
            .order_by(KycSubmission.submitted_at.desc())
        )
        if status is not None:
            q = q.where(KycSubmission.status == status)
        return [(row[0], row[1]) for row in (await self._session.execute(q)).all()]

    async def get(self, submission_id: uuid.UUID) -> tuple[KycSubmission, Member]:
        row = (
            await self._session.execute(
                select(KycSubmission, Member)
                .join(Member, KycSubmission.member_id == Member.id)
                .where(KycSubmission.id == submission_id)
            )
        ).first()
        if row is None:
            raise SubmissionNotFound(f"KYC submission '{submission_id}' not found")
        return row[0], row[1]

    async def approve(
        self, submission_id: uuid.UUID, *, reviewer_id: uuid.UUID
    ) -> KycSubmission:
        """Apply the proposed snapshot to the member row and mark approved.

        Full replace of the 11 editable fields (a proposed None clears the
        member value). Member STATUS is untouched — activation remains the
        separate maker-checker flow.
        """
        submission, member = await self.get(submission_id)
        if submission.status != "pending":
            raise SubmissionNotPending(
                f"KYC submission is '{submission.status}', not pending"
            )
        for field in _UNIQUE_FIELDS:
            value = getattr(submission, field)
            if value is not None:
                clash = await self._session.scalar(
                    select(Member.id).where(
                        getattr(Member, field) == value, Member.id != member.id
                    )
                )
                if clash is not None:
                    raise KycFieldConflict(field, str(value))
        for key in EDITABLE_KYC_FIELDS:
            setattr(member, key, getattr(submission, key))
        submission.status = "approved"
        submission.reviewed_by = reviewer_id
        submission.reviewed_at = datetime.now(UTC)
        await self._session.flush()
        _log.info(
            "member.kyc_approved",
            member_id=str(member.id),
            submission_id=str(submission.id),
        )
        return submission

    async def reject(
        self, submission_id: uuid.UUID, *, reviewer_id: uuid.UUID, reason: str
    ) -> KycSubmission:
        submission, member = await self.get(submission_id)
        if submission.status != "pending":
            raise SubmissionNotPending(
                f"KYC submission is '{submission.status}', not pending"
            )
        submission.status = "rejected"
        submission.reviewed_by = reviewer_id
        submission.reviewed_at = datetime.now(UTC)
        submission.rejection_reason = reason
        await self._session.flush()
        _log.info(
            "member.kyc_rejected",
            member_id=str(member.id),
            submission_id=str(submission.id),
        )
        return submission
