# KYC Tracking Increment 5 — Member KYC Submission + Operator Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a logged-in member submit their KYC data into an operator review queue; an operator approves (fields are applied to the member row) or rejects (with a reason) — the first and only member write path in this increment.

**Architecture:** A new tenant-schema `kyc_submissions` table (plus three new nullable `members` columns) holds proposed-field snapshots. `MemberSelfService.submit_kyc` creates/supersedes-in-place the member's single `pending` submission; `KycReviewService.approve` is the ONLY path that applies KYC fields to the member row (via ORM attribute writes so `AuditableMixin` records the diff). KYC review is **single-reviewer, not maker-checker**. The member portal Profile page gains a KYC section (status banner + completion checklist + submit `FormDialog`); the operator portal gains a review queue and a proposed-vs-current detail screen.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic (backend), pytest/httpx with stub auth headers (backend tests), Next.js 15 App Router + React 19 + `@sacco/ui` + TanStack Query (portal), vitest + Testing Library (portal tests).

This is increment 5 of 5 in the KYC tracking phase (spec:
`docs/superpowers/specs/2026-06-30-kyc-fulfilment-tracking-design.md`, which delegates the
submission/review mechanics to `docs/superpowers/specs/2026-06-29-member-self-service-design.md`,
its increment 3). Increments 1–4 are merged / in PR #61 — this plan builds on the increment-4
branch state (`member_kyc_requirements`, `app/modules/members/kyc.py`, `app/core/kyc/schemas.py`,
portal KYC components).

## Global Constraints

- Member endpoints are gated by `CurrentMember` (from `app.modules.iam.dependencies`); operator endpoints by `CurrentTenantUser`. Route handlers import the dependency aliases, never the underlying functions.
- Member endpoints never accept a client-supplied `member_id`; they scope to `current_member.id`.
- KYC review is **single-reviewer, NOT maker-checker** (2026-06-29 spec decision). Do not register approval executors; do not use `MakerCheckerConfirmDialog` in the portal — plain `ConfirmDialog` / reject dialog.
- KYC approval writes fields only. Member **status** changes stay in the existing maker-checker flow — approval never activates a member.
- Members never write identity fields directly; fields reach the member row only via `KycReviewService.approve`.
- Uniqueness (`national_id_number`, `email`) is checked at **approve** time, never at submit. Collision → HTTP 409 naming the conflict.
- KYC submit while a `pending` submission exists supersedes it **in place** (same row, new values + `submitted_at`) — 201, not an error. Submission rows are never deleted; reviewed rows are terminal history.
- Completion always comes from `member_kyc_completion` / `compute_completion` — never hand-rolled, backend or portal.
- KYC completion gates nothing (no new 402/403 paths).
- All DB access async; Pydantic schemas in `schemas.py`, routers in `api.py`; ruff + mypy (strict) stay clean.
- Portal: statuses via `<StatusBadge entity status />` (contract S — new entity `kyc_submission` added in Task 4); list screens via `<DataTable>` (contract T); forms via `FormField`/RHF/Zod with schemas in `@sacco/schemas` (contracts J, U); no client-side fetching for initial render (contract M); dates via `<FormattedDate>`/`<FormattedDateTime>` (contract H).
- Operator route registration order: literal `/members/kyc-submissions*` routes MUST be registered before `/members/{member_id}` (same shadowing rule as `/members/kyc-requirements`).

## Prerequisites

Branch from `feat/kyc-member-config` (or `main` once PR #61 merges). Docker Postgres test DB up (`docker compose ps` shows `postgres-test` healthy).

## File Structure

```
alembic/tenant/versions/018_kyc_submissions.py            (create)
app/modules/members/models.py                             (modify: +3 Member columns, +KycSubmission)
app/modules/members/kyc_submissions.py                    (create: MemberSelfService, KycReviewService, exceptions)
app/modules/members/schemas.py                            (modify: +MemberKycValues, KycSubmissionIn/Out, list/detail/reject, extend MemberSelfKycOut)
app/modules/members/api.py                                (modify: +1 member route, +4 operator routes, extend /me/kyc)
tests/modules/members/test_kyc_submissions_service.py     (create)
tests/modules/members/test_kyc_submissions_api.py         (create)

admin/packages/schemas/src/kyc.ts                         (modify: member-KYC wire types + Zod form schema + field config)
admin/packages/schemas/src/__tests__/kyc.test.ts          (modify: defaults/payload round-trip tests)
admin/packages/api-client/src/resources/member.ts         (modify: +submitKyc)
admin/packages/api-client/src/resources/members.ts        (modify: +4 kyc-submission calls)
admin/packages/api-client/src/query-keys.ts               (modify: +members.kycSubmissions/kycSubmission)
admin/packages/ui/src/components/StatusBadge/status-maps.ts (modify: +kyc_submission entity)

admin/apps/portal/app/member/(authed)/profile/page.tsx    (modify: fetch /member/me/kyc, render KYC section)
admin/apps/portal/app/member/(authed)/profile/_components/MemberKycSection.tsx (create)
admin/apps/portal/app/member/(authed)/profile/_components/MemberKycFormDialog.tsx (create)
admin/apps/portal/app/member/(authed)/profile/__tests__/MemberKycSection.test.tsx (create)

admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/page.tsx (create)
admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/_components/KycSubmissionsTable.tsx (create)
admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/__tests__/KycSubmissionsTable.test.tsx (create)
admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/[id]/page.tsx (create)
admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/[id]/_components/KycReviewActions.tsx (create)
admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/[id]/__tests__/KycReviewActions.test.tsx (create)
admin/apps/portal/src/components/shell/nav-config.tsx     (modify: Members nav children)

CLAUDE.md                                                 (modify: member-write contract, Task 8)
```

---

### Task 1: `kyc_submissions` model + three member columns + migration 018

**Files:**
- Modify: `app/modules/members/models.py`
- Create: `alembic/tenant/versions/018_kyc_submissions.py`
- Test: `tests/modules/members/test_kyc_submissions_service.py` (model section)

**Interfaces:**
- Consumes: `Base`, `AuditableMixin` (already imported in models.py).
- Produces: `Member.next_of_kin_name / next_of_kin_phone / occupation: str | None`; `KycSubmission` with `id: UUID`, `member_id: UUID`, `status: str` (`pending|approved|rejected`), `submitted_at: datetime`, `reviewed_by: UUID | None`, `reviewed_at: datetime | None`, `rejection_reason: str | None`, plus the 11 proposed-value columns (`phone`, `email`, `physical_address`, `national_id_number`, `id_document_type`, `id_document_number`, `id_issued_date`, `id_expiry_date`, `next_of_kin_name`, `next_of_kin_phone`, `occupation`), `created_at`, `updated_at`. Partial unique index: one `pending` per member.

- [ ] **Step 1: Write the failing test**

Create `tests/modules/members/test_kyc_submissions_service.py`:

```python
"""Member KYC submissions: model constraints + MemberSelfService + KycReviewService."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.members.models import KycSubmission, Member

SCHEMA = "tenant_test"


async def _set_path(s: AsyncSession) -> None:
    await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))


@pytest.fixture
async def factory(test_engine: AsyncEngine) -> AsyncGenerator[async_sessionmaker, None]:
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    yield maker
    async with maker() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text("DELETE FROM kyc_submissions"))
        await s.execute(text("DELETE FROM member_kyc_requirements"))
        await s.execute(text("DELETE FROM audit_log WHERE table_name IN ('members', 'kyc_submissions')"))
        await s.execute(text("DELETE FROM members"))
        await s.commit()


def _member(**overrides: object) -> Member:
    defaults: dict[str, object] = {
        "member_number": f"M-{uuid.uuid4().hex[:5]}",
        "full_name": "Jane Doe",
        "date_of_birth": date(1990, 5, 15),
        "gender": "female",
    }
    defaults.update(overrides)
    return Member(**defaults)


async def test_member_has_next_of_kin_and_occupation_columns(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        m = _member(next_of_kin_name="John Doe", next_of_kin_phone="+256700000001", occupation="Teacher")
        s.add(m)
        await s.commit()
        member_id = m.id
    async with factory() as s:
        await _set_path(s)
        row = (await s.execute(select(Member).where(Member.id == member_id))).scalar_one()
    assert row.next_of_kin_name == "John Doe"
    assert row.occupation == "Teacher"


async def test_at_most_one_pending_submission_per_member(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        m = _member()
        s.add(m)
        await s.flush()
        s.add(KycSubmission(member_id=m.id, phone="+256700000001"))
        await s.flush()
        s.add(KycSubmission(member_id=m.id, phone="+256700000002"))
        with pytest.raises(IntegrityError):
            await s.flush()
        await s.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/modules/members/test_kyc_submissions_service.py -q`
Expected: FAIL — `ImportError: cannot import name 'KycSubmission'`.

- [ ] **Step 3: Write the implementation**

In `app/modules/members/models.py`, add `ForeignKey` and `text` to the existing `sqlalchemy` import list, then add the three columns to `Member` directly after the `id_expiry_date` column (keeping the KYC field block together):

```python
    # KYC enrichment (increment 5; nullable, backfill-free)
    next_of_kin_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_of_kin_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    occupation: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Append after the `MemberKycRequirement` class:

```python
class KycSubmission(AuditableMixin, Base):
    """One member KYC submission awaiting / after operator review.

    At most one 'pending' row per member (partial unique index). Resubmitting
    supersedes the open pending row IN PLACE (new proposed values + refreshed
    submitted_at). Reviewed rows (approved/rejected) are terminal history and
    are never deleted or reused. The proposed-value columns are exactly the
    non-locked MEMBER_KYC_CATALOG keys.
    """

    __tablename__ = "kyc_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    submitted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Proposed editable-field snapshot
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    physical_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    national_id_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    id_document_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    id_document_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    id_issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    id_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_of_kin_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_of_kin_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    occupation: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_kyc_submissions_status",
        ),
        CheckConstraint(
            "id_document_type IS NULL OR id_document_type IN ('national_id', 'passport', 'driving_license')",
            name="ck_kyc_submissions_id_doc_type",
        ),
        Index(
            "uq_kyc_submissions_one_pending",
            "member_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_kyc_submissions_status", "status"),
        Index("ix_kyc_submissions_member_id", "member_id"),
    )
```

Create `alembic/tenant/versions/018_kyc_submissions.py`:

```python
"""Member KYC submissions + next-of-kin/occupation member columns.

Revision: 018
Depends on: 017
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("members", sa.Column("next_of_kin_name", sa.Text(), nullable=True))
    op.add_column("members", sa.Column("next_of_kin_phone", sa.Text(), nullable=True))
    op.add_column("members", sa.Column("occupation", sa.Text(), nullable=True))

    op.create_table(
        "kyc_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "member_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("members.id"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "submitted_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("physical_address", sa.Text(), nullable=True),
        sa.Column("national_id_number", sa.Text(), nullable=True),
        sa.Column("id_document_type", sa.Text(), nullable=True),
        sa.Column("id_document_number", sa.Text(), nullable=True),
        sa.Column("id_issued_date", sa.Date(), nullable=True),
        sa.Column("id_expiry_date", sa.Date(), nullable=True),
        sa.Column("next_of_kin_name", sa.Text(), nullable=True),
        sa.Column("next_of_kin_phone", sa.Text(), nullable=True),
        sa.Column("occupation", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_kyc_submissions_status",
        ),
        sa.CheckConstraint(
            "id_document_type IS NULL OR id_document_type IN ('national_id', 'passport', 'driving_license')",
            name="ck_kyc_submissions_id_doc_type",
        ),
    )
    op.create_index(
        "uq_kyc_submissions_one_pending",
        "kyc_submissions",
        ["member_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index("ix_kyc_submissions_status", "kyc_submissions", ["status"])
    op.create_index("ix_kyc_submissions_member_id", "kyc_submissions", ["member_id"])


def downgrade() -> None:
    op.drop_table("kyc_submissions")
    op.drop_column("members", "occupation")
    op.drop_column("members", "next_of_kin_phone")
    op.drop_column("members", "next_of_kin_name")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/modules/members/test_kyc_submissions_service.py -q`
Expected: PASS (2 tests).

Also run the untouched increment-4 suites (the new Member columns now really exist, so `member_kyc_values` reads real columns — behaviour must not regress):
`python -m pytest tests/modules/members/ -q` — all green.

- [ ] **Step 5: Lint, typecheck, commit**

Run: `python -m ruff check app/ tests/ && python -m mypy app/`
Expected: clean.

```bash
git add app/modules/members/models.py alembic/tenant/versions/018_kyc_submissions.py tests/modules/members/test_kyc_submissions_service.py
git commit -m "feat(members): kyc_submissions table + next-of-kin/occupation member columns"
```

---

### Task 2: `MemberSelfService` + `KycReviewService`

**Files:**
- Create: `app/modules/members/kyc_submissions.py`
- Test: `tests/modules/members/test_kyc_submissions_service.py` (append)

**Interfaces:**
- Consumes: `KycSubmission`, `Member` (Task 1); `MEMBER_KYC_CATALOG` from `app.core.kyc.catalog`.
- Produces (all consumed by Task 3's handlers):
  - `EDITABLE_KYC_FIELDS: tuple[str, ...]` — the 11 non-locked catalog keys.
  - Exceptions `SubmissionNotFound`, `SubmissionNotPending`, `KycFieldConflict(field: str, value: str)`.
  - `MemberSelfService(session).latest_submission(member_id: uuid.UUID) -> KycSubmission | None`
  - `MemberSelfService(session).submit_kyc(member_id: uuid.UUID, values: Mapping[str, object | None]) -> KycSubmission`
  - `KycReviewService(session).list(status: str | None = None) -> list[tuple[KycSubmission, Member]]`
  - `KycReviewService(session).get(submission_id: uuid.UUID) -> tuple[KycSubmission, Member]` (raises `SubmissionNotFound`)
  - `KycReviewService(session).approve(submission_id: uuid.UUID, *, reviewer_id: uuid.UUID) -> KycSubmission` (raises `SubmissionNotFound` / `SubmissionNotPending` / `KycFieldConflict`)
  - `KycReviewService(session).reject(submission_id: uuid.UUID, *, reviewer_id: uuid.UUID, reason: str) -> KycSubmission` (raises `SubmissionNotFound` / `SubmissionNotPending`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/members/test_kyc_submissions_service.py`:

```python
# ── Services ──────────────────────────────────────────────────────────────────

from app.modules.members.kyc_submissions import (  # noqa: E402
    EDITABLE_KYC_FIELDS,
    KycFieldConflict,
    KycReviewService,
    MemberSelfService,
    SubmissionNotPending,
)


def test_editable_fields_are_the_non_locked_catalog_keys() -> None:
    assert EDITABLE_KYC_FIELDS == (
        "phone",
        "email",
        "physical_address",
        "national_id_number",
        "id_document_type",
        "id_document_number",
        "id_issued_date",
        "id_expiry_date",
        "next_of_kin_name",
        "next_of_kin_phone",
        "occupation",
    )


async def test_submit_creates_pending_then_supersedes_in_place(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        m = _member()
        s.add(m)
        await s.flush()
        svc = MemberSelfService(s)
        first = await svc.submit_kyc(m.id, {"phone": "+256700000001", "occupation": "Farmer"})
        first_id = first.id
        assert first.status == "pending"
        assert first.occupation == "Farmer"
        second = await svc.submit_kyc(m.id, {"phone": "+256700000002"})
        await s.commit()
    assert second.id == first_id  # superseded in place, not a new row
    assert second.phone == "+256700000002"
    assert second.occupation is None  # full snapshot replace: omitted key clears


async def test_latest_submission_orders_by_submitted_at(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        m = _member()
        s.add(m)
        await s.flush()
        self_svc = MemberSelfService(s)
        review_svc = KycReviewService(s)
        first = await self_svc.submit_kyc(m.id, {"phone": "+256700000001"})
        await review_svc.reject(first.id, reviewer_id=uuid.uuid4(), reason="Blurry data")
        second = await self_svc.submit_kyc(m.id, {"phone": "+256700000002"})
        latest = await self_svc.latest_submission(m.id)
        await s.commit()
    assert latest is not None
    assert latest.id == second.id
    assert latest.status == "pending"


async def test_approve_applies_full_snapshot_to_member(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        m = _member(phone="+256700000000", occupation=None)
        s.add(m)
        await s.flush()
        sub = await MemberSelfService(s).submit_kyc(
            m.id,
            {
                "phone": "+256700000009",
                "national_id_number": "CM123456",
                "next_of_kin_name": "John Doe",
                "id_issued_date": date(2020, 1, 1),
            },
        )
        reviewer = uuid.uuid4()
        approved = await KycReviewService(s).approve(sub.id, reviewer_id=reviewer)
        await s.commit()
        member_id = m.id
    assert approved.status == "approved"
    assert approved.reviewed_by == reviewer
    assert approved.reviewed_at is not None
    async with factory() as s:
        await _set_path(s)
        row = (await s.execute(select(Member).where(Member.id == member_id))).scalar_one()
    assert row.phone == "+256700000009"
    assert row.national_id_number == "CM123456"
    assert row.next_of_kin_name == "John Doe"
    assert row.id_issued_date == date(2020, 1, 1)
    assert row.email is None  # full replace: proposed None clears


async def test_approve_conflicting_national_id_raises(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        other = _member(national_id_number="CM999999")
        m = _member()
        s.add_all([other, m])
        await s.flush()
        sub = await MemberSelfService(s).submit_kyc(m.id, {"national_id_number": "CM999999"})
        with pytest.raises(KycFieldConflict):
            await KycReviewService(s).approve(sub.id, reviewer_id=uuid.uuid4())
        await s.rollback()


async def test_reject_then_re_review_raises_not_pending(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        m = _member()
        s.add(m)
        await s.flush()
        sub = await MemberSelfService(s).submit_kyc(m.id, {"phone": "+256700000001"})
        rejected = await KycReviewService(s).reject(
            sub.id, reviewer_id=uuid.uuid4(), reason="Incomplete"
        )
        assert rejected.status == "rejected"
        assert rejected.rejection_reason == "Incomplete"
        with pytest.raises(SubmissionNotPending):
            await KycReviewService(s).approve(sub.id, reviewer_id=uuid.uuid4())
        await s.rollback()


async def test_list_filters_by_status_and_joins_member(
    factory: async_sessionmaker,
) -> None:
    async with factory() as s:
        await _set_path(s)
        m = _member(full_name="Queue Member")
        s.add(m)
        await s.flush()
        await MemberSelfService(s).submit_kyc(m.id, {"phone": "+256700000001"})
        rows = await KycReviewService(s).list(status="pending")
        empty = await KycReviewService(s).list(status="approved")
        await s.commit()
    assert len(rows) == 1
    submission, member = rows[0]
    assert submission.status == "pending"
    assert member.full_name == "Queue Member"
    assert empty == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/modules/members/test_kyc_submissions_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.members.kyc_submissions'`.

- [ ] **Step 3: Write the implementation**

Create `app/modules/members/kyc_submissions.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/modules/members/test_kyc_submissions_service.py -q`
Expected: PASS (9 tests).

- [ ] **Step 5: Lint, typecheck, commit**

Run: `python -m ruff check app/ tests/ && python -m mypy app/`
Expected: clean.

```bash
git add app/modules/members/kyc_submissions.py tests/modules/members/test_kyc_submissions_service.py
git commit -m "feat(members): MemberSelfService + KycReviewService for KYC submissions"
```

---

### Task 3: HTTP endpoints (member submit + operator review) + schemas

**Files:**
- Modify: `app/modules/members/schemas.py`
- Modify: `app/modules/members/api.py`
- Test: `tests/modules/members/test_kyc_submissions_api.py` (create)

**Interfaces:**
- Consumes: Task 2's services/exceptions; `KycCompletionOut` from `app.core.kyc.schemas`; `member_kyc_completion` from `app.modules.members.kyc`.
- Produces (wire contract, consumed by Task 4's TS types):
  - `POST /member/me/kyc` (body `KycSubmissionIn`) → 201 `KycSubmissionOut`
  - `GET /member/me/kyc` → `MemberSelfKycOut {completion, values: MemberKycValues, latest_submission: KycSubmissionOut | None}`
  - `GET /members/kyc-submissions?status=` → `list[KycSubmissionListItemOut]`
  - `GET /members/kyc-submissions/{submission_id}` → `KycSubmissionDetailOut {submission, member_number, full_name, current}`
  - `POST /members/kyc-submissions/{submission_id}/approve` → `KycSubmissionOut` (409 on conflict/non-pending, 404 unknown)
  - `POST /members/kyc-submissions/{submission_id}/reject` (body `KycRejectIn {reason}`) → `KycSubmissionOut`

- [ ] **Step 1: Write the failing tests**

Create `tests/modules/members/test_kyc_submissions_api.py`. Reuse the exact fixture pattern from `tests/modules/members/test_kyc_api.py` (stub auth headers; the member header is `X-Member-Actor-ID`):

```python
"""HTTP tests: member KYC submission + operator review endpoints (stub auth)."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_tenant_session
from app.main import app, lifespan

SCHEMA = "tenant_test"
HEADERS = {"X-Tenant-Slug": "test-tenant"}


async def _make_tenant_session_override(engine: AsyncEngine):  # noqa: ANN202
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(
                text(f"SET LOCAL search_path TO {SCHEMA}, platform")
            )
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


@pytest.fixture
async def client(test_engine: AsyncEngine, tenant_actor_id: uuid.UUID):  # noqa: ANN201
    app.dependency_overrides[get_tenant_session] = await _make_tenant_session_override(
        test_engine
    )
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.headers["X-Tenant-Slug"] = "test-tenant"
        c.headers["X-Tenant-Actor-ID"] = str(tenant_actor_id)
        yield c
    app.dependency_overrides.pop(get_tenant_session, None)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text("DELETE FROM kyc_submissions"))
        await s.execute(text("DELETE FROM member_kyc_requirements"))
        await s.execute(text("DELETE FROM member_sessions"))
        await s.execute(
            text("DELETE FROM audit_log WHERE table_name IN ('members', 'kyc_submissions')")
        )
        await s.execute(text("DELETE FROM members"))
        await s.commit()


async def _create_active_member(
    client: AsyncClient, test_engine: AsyncEngine, **fields: Any
) -> dict[str, Any]:
    body = {
        "full_name": f"Member {uuid.uuid4().hex[:6]}",
        "date_of_birth": "1990-05-15",
        "gender": "female",
        "email": f"m-{uuid.uuid4().hex[:6]}@example.com",
        **fields,
    }
    resp = await client.post("/members", json=body, headers=HEADERS)
    assert resp.status_code == 201, resp.text
    member = resp.json()
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(
            text(
                "UPDATE members SET status='active', portal_enabled=true WHERE id = :mid"
            ),
            {"mid": member["id"]},
        )
        await s.commit()
    return member


def _member_headers(member_id: str) -> dict[str, str]:
    return {**HEADERS, "X-Member-Actor-ID": member_id}


async def test_member_submit_creates_pending(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member = await _create_active_member(client, test_engine)
    resp = await client.post(
        "/member/me/kyc",
        json={"phone": "+256700000001", "occupation": "Farmer"},
        headers=_member_headers(member["id"]),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["proposed"]["phone"] == "+256700000001"
    assert body["proposed"]["occupation"] == "Farmer"
    assert body["proposed"]["national_id_number"] is None


async def test_member_me_kyc_includes_values_and_latest_submission(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member = await _create_active_member(client, test_engine)
    headers = _member_headers(member["id"])
    resp = await client.get("/member/me/kyc", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["latest_submission"] is None
    assert body["values"]["email"] == member["email"]

    await client.post("/member/me/kyc", json={"phone": "+256700000001"}, headers=headers)
    body = (await client.get("/member/me/kyc", headers=headers)).json()
    assert body["latest_submission"]["status"] == "pending"


async def test_member_resubmit_supersedes_in_place(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member = await _create_active_member(client, test_engine)
    headers = _member_headers(member["id"])
    first = (
        await client.post("/member/me/kyc", json={"phone": "+25670000A"}, headers=headers)
    ).json()
    second = (
        await client.post("/member/me/kyc", json={"phone": "+25670000B"}, headers=headers)
    ).json()
    assert second["id"] == first["id"]
    assert second["proposed"]["phone"] == "+25670000B"


async def test_operator_queue_lists_and_filters(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member = await _create_active_member(client, test_engine)
    await client.post(
        "/member/me/kyc", json={"phone": "+256700000001"}, headers=_member_headers(member["id"])
    )
    # Route-order regression: literal segment must not be swallowed by /{member_id}.
    resp = await client.get("/members/kyc-submissions", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["member_number"] == member["member_number"]
    assert rows[0]["full_name"] == member["full_name"]

    filtered = await client.get(
        "/members/kyc-submissions", params={"status": "approved"}, headers=HEADERS
    )
    assert filtered.json() == []


async def test_operator_detail_shows_proposed_vs_current(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member = await _create_active_member(client, test_engine, phone="+256700000000")
    sub = (
        await client.post(
            "/member/me/kyc",
            json={"phone": "+256700000009"},
            headers=_member_headers(member["id"]),
        )
    ).json()
    resp = await client.get(f"/members/kyc-submissions/{sub['id']}", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["submission"]["proposed"]["phone"] == "+256700000009"
    assert body["current"]["phone"] == "+256700000000"
    assert body["member_number"] == member["member_number"]


async def test_approve_applies_fields_and_is_terminal(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member = await _create_active_member(client, test_engine)
    sub = (
        await client.post(
            "/member/me/kyc",
            json={"phone": "+256700000009", "next_of_kin_name": "John Doe"},
            headers=_member_headers(member["id"]),
        )
    ).json()
    resp = await client.post(
        f"/members/kyc-submissions/{sub['id']}/approve", headers=HEADERS
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"

    updated = (await client.get(f"/members/{member['id']}", headers=HEADERS)).json()
    assert updated["phone"] == "+256700000009"
    assert updated["status"] == "active"  # approval never touches status

    again = await client.post(
        f"/members/kyc-submissions/{sub['id']}/approve", headers=HEADERS
    )
    assert again.status_code == 409


async def test_approve_duplicate_national_id_409(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    await _create_active_member(client, test_engine, national_id_number="CM999999")
    member = await _create_active_member(client, test_engine)
    sub = (
        await client.post(
            "/member/me/kyc",
            json={"national_id_number": "CM999999"},
            headers=_member_headers(member["id"]),
        )
    ).json()
    resp = await client.post(
        f"/members/kyc-submissions/{sub['id']}/approve", headers=HEADERS
    )
    assert resp.status_code == 409
    assert "national_id_number" in resp.json()["detail"]


async def test_reject_requires_reason_and_surfaces_to_member(
    client: AsyncClient, test_engine: AsyncEngine
) -> None:
    member = await _create_active_member(client, test_engine)
    headers = _member_headers(member["id"])
    sub = (
        await client.post("/member/me/kyc", json={"phone": "+256700000001"}, headers=headers)
    ).json()

    missing = await client.post(
        f"/members/kyc-submissions/{sub['id']}/reject", json={}, headers=HEADERS
    )
    assert missing.status_code == 422

    resp = await client.post(
        f"/members/kyc-submissions/{sub['id']}/reject",
        json={"reason": "ID number looks wrong"},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"

    me = (await client.get("/member/me/kyc", headers=headers)).json()
    assert me["latest_submission"]["status"] == "rejected"
    assert me["latest_submission"]["rejection_reason"] == "ID number looks wrong"


async def test_unknown_submission_404(client: AsyncClient) -> None:
    resp = await client.get(f"/members/kyc-submissions/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404
    resp = await client.post(
        f"/members/kyc-submissions/{uuid.uuid4()}/approve", headers=HEADERS
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/modules/members/test_kyc_submissions_api.py -q`
Expected: FAIL — 404s/422s from missing routes and missing response fields (`latest_submission`).

- [ ] **Step 3: Write the implementation**

In `app/modules/members/schemas.py`, add after the existing imports/type aliases:

```python
class MemberKycValues(BaseModel):
    """The 11 editable (non-locked) member KYC fields — one shape for
    proposed snapshots, current values, and the member self view."""

    phone: str | None = None
    email: str | None = None
    physical_address: str | None = None
    national_id_number: str | None = None
    id_document_type: IdDocumentType | None = None
    id_document_number: str | None = None
    id_issued_date: date | None = None
    id_expiry_date: date | None = None
    next_of_kin_name: str | None = None
    next_of_kin_phone: str | None = None
    occupation: str | None = None

    model_config = {"from_attributes": True}


class KycSubmissionIn(MemberKycValues):
    """Proposed values — the FULL intended state of the editable fields.

    An omitted/None field clears the member value at approve time (the
    portal form prefills current values, so a blank is intentional).
    """


class KycSubmissionOut(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    status: str
    submitted_at: datetime
    reviewed_at: datetime | None
    rejection_reason: str | None
    proposed: MemberKycValues

    @classmethod
    def from_row(cls, s: KycSubmission) -> KycSubmissionOut:
        return cls(
            id=s.id,
            member_id=s.member_id,
            status=s.status,
            submitted_at=s.submitted_at,
            reviewed_at=s.reviewed_at,
            rejection_reason=s.rejection_reason,
            proposed=MemberKycValues.model_validate(s),
        )


class KycSubmissionListItemOut(BaseModel):
    id: uuid.UUID
    member_id: uuid.UUID
    member_number: str
    full_name: str
    status: str
    submitted_at: datetime


class KycSubmissionDetailOut(BaseModel):
    submission: KycSubmissionOut
    member_number: str
    full_name: str
    current: MemberKycValues


class KycRejectIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
```

Add the model import at the top of `schemas.py`:

```python
from app.modules.members.models import KycSubmission
```

Replace the existing `MemberSelfKycOut` with:

```python
class MemberSelfKycOut(BaseModel):
    """Member self view: completion + current values + latest submission."""

    completion: KycCompletionOut
    values: MemberKycValues
    latest_submission: KycSubmissionOut | None
```

In `app/modules/members/api.py`:

Extend the imports:

```python
from app.modules.members.kyc_submissions import (
    KycFieldConflict,
    KycReviewService,
    MemberSelfService,
    SubmissionNotFound,
    SubmissionNotPending,
)
from app.modules.members.schemas import (
    KycRejectIn,
    KycSubmissionDetailOut,
    KycSubmissionIn,
    KycSubmissionListItemOut,
    KycSubmissionOut,
    MemberIn,
    MemberKycOut,
    MemberKycValues,
    MemberOut,
    MemberSelfKycOut,
    StatusChangeIn,
    StatusChangeOut,
)
```

Add `Literal` to the `typing` import.

Replace the `member_self_kyc` handler and add the submit handler:

```python
@member_router.get("/me/kyc", response_model=MemberSelfKycOut)
async def member_self_kyc(member: CurrentMember, session: Session) -> MemberSelfKycOut:
    completion = await member_kyc_completion(session, member)
    latest = await MemberSelfService(session).latest_submission(member.id)
    return MemberSelfKycOut(
        completion=KycCompletionOut.from_completion(completion),
        values=MemberKycValues.model_validate(member),
        latest_submission=KycSubmissionOut.from_row(latest) if latest else None,
    )


@member_router.post("/me/kyc", response_model=KycSubmissionOut, status_code=201)
async def member_submit_kyc(
    body: KycSubmissionIn, member: CurrentMember, session: Session
) -> KycSubmissionOut:
    """Submit/resubmit KYC. Supersedes any open pending submission in place —
    naturally idempotent, so a retried POST converges on the same state."""
    submission = await MemberSelfService(session).submit_kyc(
        member.id, body.model_dump()
    )
    return KycSubmissionOut.from_row(submission)
```

Insert the four operator routes **between** `put_member_kyc_requirements` and `get_member` (route-order rule — the literal `kyc-submissions` segment must beat `/{member_id}`):

```python
@router.get("/kyc-submissions", response_model=list[KycSubmissionListItemOut])
async def list_kyc_submissions(
    session: Session,
    _user: CurrentTenantUser,
    status: Literal["pending", "approved", "rejected"] | None = None,
) -> list[KycSubmissionListItemOut]:
    # NOTE: registered before /{member_id} — same shadowing rule as
    # /kyc-requirements (a UUID path param would swallow this literal and 422).
    rows = await KycReviewService(session).list(status=status)
    return [
        KycSubmissionListItemOut(
            id=s.id,
            member_id=m.id,
            member_number=m.member_number,
            full_name=m.full_name,
            status=s.status,
            submitted_at=s.submitted_at,
        )
        for s, m in rows
    ]


@router.get("/kyc-submissions/{submission_id}", response_model=KycSubmissionDetailOut)
async def get_kyc_submission(
    submission_id: uuid.UUID, session: Session, _user: CurrentTenantUser
) -> KycSubmissionDetailOut:
    try:
        submission, member = await KycReviewService(session).get(submission_id)
    except SubmissionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return KycSubmissionDetailOut(
        submission=KycSubmissionOut.from_row(submission),
        member_number=member.member_number,
        full_name=member.full_name,
        current=MemberKycValues.model_validate(member),
    )


@router.post("/kyc-submissions/{submission_id}/approve", response_model=KycSubmissionOut)
async def approve_kyc_submission(
    submission_id: uuid.UUID, session: Session, user: CurrentTenantUser
) -> KycSubmissionOut:
    """Single-reviewer approval (NOT maker-checker, per the 2026-06-29 spec).
    Applies the proposed snapshot to the member row; never touches status."""
    try:
        submission = await KycReviewService(session).approve(
            submission_id, reviewer_id=user.id
        )
    except SubmissionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (SubmissionNotPending, KycFieldConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return KycSubmissionOut.from_row(submission)


@router.post("/kyc-submissions/{submission_id}/reject", response_model=KycSubmissionOut)
async def reject_kyc_submission(
    submission_id: uuid.UUID,
    body: KycRejectIn,
    session: Session,
    user: CurrentTenantUser,
) -> KycSubmissionOut:
    try:
        submission = await KycReviewService(session).reject(
            submission_id, reviewer_id=user.id, reason=body.reason
        )
    except SubmissionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SubmissionNotPending as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return KycSubmissionOut.from_row(submission)
```

- [ ] **Step 4: Run tests to verify they pass — including the untouched increment-4 suites**

Run: `python -m pytest tests/modules/members/ -q`
Expected: all green (the changed `GET /member/me/kyc` response is additive — `test_member_me_kyc` in `test_kyc_api.py` only asserts on `completion`).

- [ ] **Step 5: Lint, typecheck, commit**

Run: `python -m ruff check app/ tests/ && python -m mypy app/`
Expected: clean.

```bash
git add app/modules/members/schemas.py app/modules/members/api.py tests/modules/members/test_kyc_submissions_api.py
git commit -m "feat(members): member KYC submit + operator review endpoints"
```

---

### Task 4: Portal wire types, Zod form schema, api-client resources, StatusBadge entity

**Files:**
- Modify: `admin/packages/schemas/src/kyc.ts`
- Modify: `admin/packages/schemas/src/__tests__/kyc.test.ts`
- Modify: `admin/packages/api-client/src/resources/member.ts`
- Modify: `admin/packages/api-client/src/resources/members.ts`
- Modify: `admin/packages/api-client/src/query-keys.ts`
- Modify: `admin/packages/ui/src/components/StatusBadge/status-maps.ts`

**Interfaces:**
- Consumes: Task 3's wire shapes.
- Produces (consumed by Tasks 5–7):
  - Types: `MemberKycEditableKey`, `MemberKycValues`, `KycSubmissionStatus`, `KycSubmissionOut`, `KycSubmissionListItemOut`, `KycSubmissionDetailOut`; `MemberSelfKycOut` extended with `values` + `latest_submission`.
  - Form: `memberKycFormSchema`, `MemberKycFormInput`, `MEMBER_KYC_FIELDS` (11 specs with `kind: "text" | "email" | "date" | "select"`), `memberKycFormDefaults(values)`, `toMemberKycPayload(input)`, `ID_DOCUMENT_TYPES`.
  - Resources: `member.submitKyc(body)`; `members.listKycSubmissions(query?)`, `members.getKycSubmission(id)`, `members.approveKycSubmission(id)`, `members.rejectKycSubmission(id, body)`.
  - Query keys: `queryKeys.members.kycSubmissions()`, `queryKeys.members.kycSubmission(id)`.
  - StatusBadge: `entity="kyc_submission"` renders `pending`/`approved`/`rejected`.

- [ ] **Step 1: Write the failing test**

Append to `admin/packages/schemas/src/__tests__/kyc.test.ts`:

```ts
import {
  MEMBER_KYC_FIELDS,
  memberKycFormDefaults,
  memberKycFormSchema,
  toMemberKycPayload,
  type MemberKycValues,
} from "../kyc";

const EMPTY_VALUES: MemberKycValues = {
  phone: null,
  email: null,
  physical_address: null,
  national_id_number: null,
  id_document_type: null,
  id_document_number: null,
  id_issued_date: null,
  id_expiry_date: null,
  next_of_kin_name: null,
  next_of_kin_phone: null,
  occupation: null,
};

describe("member KYC form helpers", () => {
  it("has one field spec per editable catalog key", () => {
    expect(MEMBER_KYC_FIELDS.map((f) => f.key)).toEqual([
      "phone",
      "email",
      "physical_address",
      "national_id_number",
      "id_document_type",
      "id_document_number",
      "id_issued_date",
      "id_expiry_date",
      "next_of_kin_name",
      "next_of_kin_phone",
      "occupation",
    ]);
  });

  it("round-trips server nulls -> form blanks -> payload nulls", () => {
    const defaults = memberKycFormDefaults(EMPTY_VALUES);
    expect(defaults.phone).toBe("");
    const payload = toMemberKycPayload(defaults);
    expect(payload).toEqual(EMPTY_VALUES);
  });

  it("keeps provided values through the round trip", () => {
    const defaults = memberKycFormDefaults({
      ...EMPTY_VALUES,
      phone: "+256700000001",
      id_document_type: "passport",
    });
    const payload = toMemberKycPayload(defaults);
    expect(payload.phone).toBe("+256700000001");
    expect(payload.id_document_type).toBe("passport");
  });

  it("rejects a malformed date but accepts blank", () => {
    const base = memberKycFormDefaults(EMPTY_VALUES);
    expect(
      memberKycFormSchema.safeParse({ ...base, id_issued_date: "01/02/2020" }).success,
    ).toBe(false);
    expect(
      memberKycFormSchema.safeParse({ ...base, id_issued_date: "" }).success,
    ).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `admin/`): `pnpm --filter @sacco/schemas test`
Expected: FAIL — `MEMBER_KYC_FIELDS` not exported.

- [ ] **Step 3: Write the implementation**

Append to `admin/packages/schemas/src/kyc.ts` (after the increment-4 member-KYC block):

```ts
// ---- Member KYC submissions (increment 5). Wire shapes mirror
// app/modules/members/schemas.py; dates are ISO strings over the wire. ----

// NOTE: do NOT reuse member.ts's idDocumentTypeSchema here — it includes
// "voters_card", which the backend's ck_members_id_doc_type / Pydantic
// Literal reject. Also do NOT export a type named IdDocumentType from this
// file — member.ts already exports one and index.ts re-exports both files
// (`export *`), so a second export with that name breaks the build.
export const ID_DOCUMENT_TYPES = ["national_id", "passport", "driving_license"] as const;

export type MemberKycEditableKey =
  | "phone"
  | "email"
  | "physical_address"
  | "national_id_number"
  | "id_document_type"
  | "id_document_number"
  | "id_issued_date"
  | "id_expiry_date"
  | "next_of_kin_name"
  | "next_of_kin_phone"
  | "occupation";

export type MemberKycValues = { [K in MemberKycEditableKey]: string | null };

export type KycSubmissionStatus = "pending" | "approved" | "rejected";

export interface KycSubmissionOut {
  id: string;
  member_id: string;
  status: KycSubmissionStatus;
  submitted_at: string;
  reviewed_at: string | null;
  rejection_reason: string | null;
  proposed: MemberKycValues;
}

export interface KycSubmissionListItemOut {
  id: string;
  member_id: string;
  member_number: string;
  full_name: string;
  status: KycSubmissionStatus;
  submitted_at: string;
}

export interface KycSubmissionDetailOut {
  submission: KycSubmissionOut;
  member_number: string;
  full_name: string;
  current: MemberKycValues;
}

// The member KYC form models "not provided" as "" and toMemberKycPayload
// converts back to null (same convention as the organization KYC form).
export const memberKycFormSchema = z.object({
  phone: z.string().trim(),
  email: z
    .string()
    .trim()
    .toLowerCase()
    .email("Enter a valid email address")
    .or(z.literal("")),
  physical_address: z.string().trim(),
  national_id_number: z.string().trim(),
  id_document_type: z.enum(ID_DOCUMENT_TYPES).or(z.literal("")),
  id_document_number: z.string().trim(),
  id_issued_date: z
    .string()
    .regex(ISO_DATE_RE, "Use the date picker (YYYY-MM-DD)")
    .or(z.literal("")),
  id_expiry_date: z
    .string()
    .regex(ISO_DATE_RE, "Use the date picker (YYYY-MM-DD)")
    .or(z.literal("")),
  next_of_kin_name: z.string().trim(),
  next_of_kin_phone: z.string().trim(),
  occupation: z.string().trim(),
});
export type MemberKycFormInput = z.infer<typeof memberKycFormSchema>;

export interface MemberKycFieldSpec {
  key: MemberKycEditableKey;
  label: string;
  kind: "text" | "email" | "date" | "select";
}

// Labels mirror MEMBER_KYC_CATALOG in app/core/kyc/catalog.py verbatim.
export const MEMBER_KYC_FIELDS: readonly MemberKycFieldSpec[] = [
  { key: "phone", label: "Phone", kind: "text" },
  { key: "email", label: "Email", kind: "email" },
  { key: "physical_address", label: "Physical address", kind: "text" },
  { key: "national_id_number", label: "National ID number", kind: "text" },
  { key: "id_document_type", label: "ID document type", kind: "select" },
  { key: "id_document_number", label: "ID document number", kind: "text" },
  { key: "id_issued_date", label: "ID issued date", kind: "date" },
  { key: "id_expiry_date", label: "ID expiry date", kind: "date" },
  { key: "next_of_kin_name", label: "Next of kin name", kind: "text" },
  { key: "next_of_kin_phone", label: "Next of kin phone", kind: "text" },
  { key: "occupation", label: "Occupation", kind: "text" },
];

/** Server nulls → form empty strings. */
export function memberKycFormDefaults(values: MemberKycValues): MemberKycFormInput {
  const out = {} as Record<MemberKycEditableKey, string>;
  for (const field of MEMBER_KYC_FIELDS) {
    out[field.key] = values[field.key] ?? "";
  }
  return out as MemberKycFormInput;
}

/** Form empty/blank strings → null on the wire. */
export function toMemberKycPayload(input: MemberKycFormInput): MemberKycValues {
  const out = {} as Record<MemberKycEditableKey, string | null>;
  for (const field of MEMBER_KYC_FIELDS) {
    const raw = input[field.key].trim();
    out[field.key] = raw === "" ? null : raw;
  }
  return out as MemberKycValues;
}
```

Replace the existing `MemberSelfKycOut` interface in the same file with:

```ts
export interface MemberSelfKycOut {
  completion: KycCompletionOut;
  values: MemberKycValues;
  latest_submission: KycSubmissionOut | null;
}
```

In `admin/packages/api-client/src/resources/member.ts`, add inside the returned object (after `getMyKyc`):

```ts
    submitKyc: (body: Record<string, unknown>) =>
      api.POST("/member/me/kyc" as never, { body } as never),
```

In `admin/packages/api-client/src/resources/members.ts`, add inside the returned object (after `getKyc`):

```ts
    listKycSubmissions: (query?: Record<string, unknown>) =>
      api.GET("/members/kyc-submissions" as never, { params: { query } } as never),
    getKycSubmission: (id: string) =>
      api.GET("/members/kyc-submissions/{submission_id}" as never, {
        params: { path: { submission_id: id } },
      } as never),
    approveKycSubmission: (id: string) =>
      api.POST("/members/kyc-submissions/{submission_id}/approve" as never, {
        params: { path: { submission_id: id } },
      } as never),
    rejectKycSubmission: (id: string, body: { reason: string }) =>
      api.POST("/members/kyc-submissions/{submission_id}/reject" as never, {
        params: { path: { submission_id: id } },
        body,
      } as never),
```

In `admin/packages/api-client/src/query-keys.ts`, add to the `members` group (after the existing `kyc` key):

```ts
    kycSubmissions: () => ["members", "kycSubmissions"] as const,
    kycSubmission: (id: string) => ["members", "kycSubmissions", id] as const,
```

In `admin/packages/ui/src/components/StatusBadge/status-maps.ts`:
- Add `| "kyc_submission"` to the `StatusEntity` union.
- Add after `REPORT_RUN_STATUS`:

```ts
export const KYC_SUBMISSION_STATUS: StatusMap = {
  pending: { variant: "info", label: "Pending Review" },
  approved: { variant: "success", label: "Approved" },
  rejected: { variant: "danger", label: "Rejected" },
};
```

- Add `kyc_submission: KYC_SUBMISSION_STATUS,` to the `ENTITY_MAPS` record.

- [ ] **Step 4: Run tests to verify they pass**

Run (from `admin/`): `pnpm --filter @sacco/schemas test && pnpm --filter @sacco/api-client test && pnpm --filter @sacco/ui test`
Expected: all green.

- [ ] **Step 5: Package checks + commit**

Run (from `admin/`): `pnpm lint && pnpm typecheck`
Expected: exit 0.

```bash
git add admin/packages/schemas/src/kyc.ts admin/packages/schemas/src/__tests__/kyc.test.ts admin/packages/api-client/src/resources/member.ts admin/packages/api-client/src/resources/members.ts admin/packages/api-client/src/query-keys.ts admin/packages/ui/src/components/StatusBadge/status-maps.ts
git commit -m "feat(api-client): member KYC submission types, resources, kyc_submission badge"
```

---

### Task 5: Member portal — Profile → KYC section

**Files:**
- Modify: `admin/apps/portal/app/member/(authed)/profile/page.tsx`
- Create: `admin/apps/portal/app/member/(authed)/profile/_components/MemberKycSection.tsx`
- Create: `admin/apps/portal/app/member/(authed)/profile/_components/MemberKycFormDialog.tsx`
- Test: `admin/apps/portal/app/member/(authed)/profile/__tests__/MemberKycSection.test.tsx`

**Interfaces:**
- Consumes: `resources.member.getMyKyc()` / `resources.member.submitKyc(body)` (Task 4); `MemberSelfKycOut`, `memberKycFormSchema`, `memberKycFormDefaults`, `toMemberKycPayload`, `MEMBER_KYC_FIELDS`, `ID_DOCUMENT_TYPES` from `@sacco/schemas`; `KycCompletionCard` from `@/components/kyc/KycCompletionCard`; `FormDialog`, `FormField`, `Input`, `DateInput`, `Select*`, `Button`, `StatusBadge`, `toast` from `@sacco/ui`; `queryKeys.member.kyc()`.
- Produces: `MemberKycSection({ initial }: { initial: MemberSelfKycOut })` client component rendered by the profile server page.

Status-banner states (2026-06-29 spec):
- `latest_submission === null` → "Complete your KYC" callout + **Complete KYC** button.
- `status === "pending"` → "Under review" banner (`StatusBadge entity="kyc_submission" status="pending"`), submit button hidden.
- `status === "rejected"` → rejection reason + **Resubmit KYC** button (form prefilled with the rejected proposal).
- `status === "approved"` → confirmation note + **Edit KYC** button (edits create a new pending).

- [ ] **Step 1: Write the failing test**

Create `admin/apps/portal/app/member/(authed)/profile/__tests__/MemberKycSection.test.tsx`. Mirror the mock pattern used by the increment-4 test `admin/apps/portal/app/(tenant-authed)/organization/member-kyc-requirements/__tests__` (mock `@/auth/use-auth` to inject `resources`, wrap in the test QueryClient provider used across portal tests):

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { MemberSelfKycOut } from "@sacco/schemas";
import { MemberKycSection } from "../_components/MemberKycSection";
import { renderWithProviders } from "@/test/render-with-providers";

const submitKyc = vi.fn().mockResolvedValue({ data: { id: "s1", status: "pending" } });

vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { member: { submitKyc } } }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

const EMPTY_VALUES = {
  phone: null,
  email: null,
  physical_address: null,
  national_id_number: null,
  id_document_type: null,
  id_document_number: null,
  id_issued_date: null,
  id_expiry_date: null,
  next_of_kin_name: null,
  next_of_kin_phone: null,
  occupation: null,
};

function baseKyc(overrides: Partial<MemberSelfKycOut> = {}): MemberSelfKycOut {
  return {
    completion: {
      items: [
        { key: "phone", label: "Phone", required: true, present: false },
      ],
      required_total: 1,
      required_present: 0,
      percent: 0,
      missing_required: ["phone"],
      is_complete: false,
    },
    values: EMPTY_VALUES,
    latest_submission: null,
    ...overrides,
  };
}

describe("MemberKycSection", () => {
  it("shows the complete-your-KYC CTA when there is no submission", () => {
    renderWithProviders(<MemberKycSection initial={baseKyc()} />);
    expect(screen.getByRole("button", { name: /complete kyc/i })).toBeInTheDocument();
  });

  it("shows under-review and hides the submit button while pending", () => {
    renderWithProviders(
      <MemberKycSection
        initial={baseKyc({
          latest_submission: {
            id: "s1",
            member_id: "m1",
            status: "pending",
            submitted_at: "2026-07-08T10:00:00Z",
            reviewed_at: null,
            rejection_reason: null,
            proposed: EMPTY_VALUES,
          },
        })}
      />,
    );
    expect(screen.getByText(/under review/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /kyc/i })).not.toBeInTheDocument();
  });

  it("shows the rejection reason and a resubmit button when rejected", () => {
    renderWithProviders(
      <MemberKycSection
        initial={baseKyc({
          latest_submission: {
            id: "s1",
            member_id: "m1",
            status: "rejected",
            submitted_at: "2026-07-08T10:00:00Z",
            reviewed_at: "2026-07-08T11:00:00Z",
            rejection_reason: "ID number looks wrong",
            proposed: EMPTY_VALUES,
          },
        })}
      />,
    );
    expect(screen.getByText("ID number looks wrong")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /resubmit kyc/i })).toBeInTheDocument();
  });

  it("opens the form dialog and submits the payload", async () => {
    const user = userEvent.setup();
    renderWithProviders(<MemberKycSection initial={baseKyc()} />);
    await user.click(screen.getByRole("button", { name: /complete kyc/i }));
    await user.type(screen.getByLabelText(/phone/i), "+256700000001");
    await user.click(screen.getByRole("button", { name: /submit for review/i }));
    expect(submitKyc).toHaveBeenCalledWith(
      expect.objectContaining({ phone: "+256700000001" }),
    );
  });
});
```

(If `renderWithProviders` does not exist under `@/test/`, use the exact provider-wrapping helper the existing portal component tests use — check a neighbouring `__tests__` file and copy its setup rather than inventing a new one.)

- [ ] **Step 2: Run test to verify it fails**

Run (from `admin/`): `pnpm --filter @sacco/portal test -- MemberKycSection`
Expected: FAIL — cannot resolve `../_components/MemberKycSection`.

- [ ] **Step 3: Write the implementation**

Create `admin/apps/portal/app/member/(authed)/profile/_components/MemberKycFormDialog.tsx`:

```tsx
"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  DateInput,
  FormDialog,
  FormField,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@sacco/ui";
import {
  ID_DOCUMENT_TYPES,
  MEMBER_KYC_FIELDS,
  memberKycFormDefaults,
  memberKycFormSchema,
  type MemberKycFormInput,
  type MemberKycValues,
} from "@sacco/schemas";

const ID_DOCUMENT_LABELS: Record<(typeof ID_DOCUMENT_TYPES)[number], string> = {
  national_id: "National ID",
  passport: "Passport",
  driving_license: "Driving license",
};

export function MemberKycFormDialog({
  initialValues,
  busy,
  onDismiss,
  onSubmit,
}: {
  initialValues: MemberKycValues;
  busy: boolean;
  onDismiss: () => void;
  onSubmit: (input: MemberKycFormInput) => void;
}) {
  const form = useForm<MemberKycFormInput>({
    resolver: zodResolver(memberKycFormSchema),
    defaultValues: memberKycFormDefaults(initialValues),
  });

  return (
    <FormDialog
      title="Complete your KYC"
      description="Your details are reviewed by SACCO staff before they are applied."
      onDismiss={onDismiss}
      onSubmit={form.handleSubmit(onSubmit)}
      footer={
        <>
          <Button type="button" variant="secondary" onClick={onDismiss} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy}>
            Submit for review
          </Button>
        </>
      }
    >
      {MEMBER_KYC_FIELDS.map((field) => (
        <FormField
          key={field.key}
          control={form.control}
          name={field.key}
          label={field.label}
          render={({ field: rhf }) =>
            field.kind === "select" ? (
              <Select
                value={rhf.value === "" ? undefined : rhf.value}
                onValueChange={rhf.onChange}
              >
                <SelectTrigger id={rhf.name}>
                  <SelectValue placeholder="Select a document type" />
                </SelectTrigger>
                <SelectContent>
                  {ID_DOCUMENT_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {ID_DOCUMENT_LABELS[t]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : field.kind === "date" ? (
              <DateInput {...rhf} />
            ) : (
              <Input type={field.kind === "email" ? "email" : "text"} {...rhf} />
            )
          }
        />
      ))}
    </FormDialog>
  );
}
```

(Adjust the `FormField` render-prop and `DateInput` prop signatures to the exact shapes used in `admin/apps/portal/app/(tenant-authed)/organization/kyc/_components/` — the increment-3 organization KYC form is the canonical consumer; copy its field-wiring precisely.)

Create `admin/apps/portal/app/member/(authed)/profile/_components/MemberKycSection.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Card, StatusBadge, toast } from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  toMemberKycPayload,
  type KycSubmissionOut,
  type MemberKycFormInput,
  type MemberSelfKycOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";
import { KycCompletionCard } from "@/components/kyc/KycCompletionCard";
import { MemberKycFormDialog } from "./MemberKycFormDialog";

export function MemberKycSection({ initial }: { initial: MemberSelfKycOut }) {
  const router = useRouter();
  const { resources } = useAuth();
  const [formOpen, setFormOpen] = useState(false);

  const submission = initial.latest_submission;
  const isPending = submission?.status === "pending";

  const mutation = useTypedMutation<KycSubmissionOut, MemberKycFormInput>(
    async (input) => {
      const res = await (resources.member.submitKyc(
        toMemberKycPayload(input) as unknown as Record<string, unknown>,
      ) as Promise<{ data?: KycSubmissionOut; error?: unknown }>);
      if (res.error || !res.data) throw res.error ?? new Error("Empty response");
      return res.data;
    },
    {
      invalidates: [queryKeys.member.kyc()],
      onSuccess: () => {
        toast.success("KYC submitted", {
          description: "SACCO staff will review your details.",
        });
        setFormOpen(false);
        router.refresh();
      },
      onError: (error) => {
        toast.error("Your KYC was not submitted", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const ctaLabel =
    submission == null
      ? "Complete KYC"
      : submission.status === "rejected"
        ? "Resubmit KYC"
        : "Edit KYC";
  // Prefill the rejected proposal so the member fixes it rather than
  // retyping; otherwise start from the current approved/on-record values.
  const formValues =
    submission?.status === "rejected" ? submission.proposed : initial.values;

  return (
    <section className="space-y-4">
      <h2 className="text-[length:var(--text-h5)] font-semibold">KYC</h2>

      {submission == null ? (
        <Card className="flex items-center justify-between gap-4 p-4">
          <p>Complete your KYC so the SACCO can verify your details.</p>
          <Button onClick={() => setFormOpen(true)}>Complete KYC</Button>
        </Card>
      ) : isPending ? (
        <Card className="flex items-center justify-between gap-4 p-4">
          <p>Your KYC is under review.</p>
          <StatusBadge entity="kyc_submission" status="pending" />
        </Card>
      ) : submission.status === "rejected" ? (
        <Card className="space-y-3 p-4">
          <div className="flex items-center justify-between gap-4">
            <p>Your KYC submission was rejected.</p>
            <StatusBadge entity="kyc_submission" status="rejected" />
          </div>
          <p className="text-[var(--text-secondary)]">{submission.rejection_reason}</p>
          <Button onClick={() => setFormOpen(true)}>Resubmit KYC</Button>
        </Card>
      ) : (
        <Card className="flex items-center justify-between gap-4 p-4">
          <p>Your KYC details were approved.</p>
          <div className="flex items-center gap-3">
            <StatusBadge entity="kyc_submission" status="approved" />
            <Button variant="secondary" onClick={() => setFormOpen(true)}>
              {ctaLabel}
            </Button>
          </div>
        </Card>
      )}

      <KycCompletionCard completion={initial.completion} />

      {formOpen && !isPending ? (
        <MemberKycFormDialog
          initialValues={formValues}
          busy={mutation.isPending}
          onDismiss={() => setFormOpen(false)}
          onSubmit={(input) => mutation.mutate(input)}
        />
      ) : null}
    </section>
  );
}
```

Modify `admin/apps/portal/app/member/(authed)/profile/page.tsx` — fetch KYC alongside the member context and render the section under the profile card:

```tsx
import type { MemberSelfKycOut } from "@sacco/schemas";
import { MemberKycSection } from "./_components/MemberKycSection";
```

Inside `MemberProfilePage`, after `const { member } = await getMemberPageContext();` (the context also exposes `resources` — destructure it):

```tsx
  const { member, resources } = await getMemberPageContext();
  const { data: kyc } = await (resources.member.getMyKyc() as Promise<{
    data?: MemberSelfKycOut;
    error?: unknown;
  }>);
```

And after the existing profile `<Card>`, inside the top-level `div`:

```tsx
      {kyc ? <MemberKycSection initial={kyc} /> : null}
```

(If `getMemberPageContext()` does not return `resources`, use the same server-fetch helper the member dashboard page uses to call `member.getMyKyc` — copy that pattern exactly.)

- [ ] **Step 4: Run tests to verify they pass**

Run (from `admin/`): `pnpm --filter @sacco/portal test -- MemberKycSection`
Expected: PASS (4 tests). Then run the profile/auth suites to catch regressions:
`pnpm --filter @sacco/portal test -- profile`

- [ ] **Step 5: Checks + commit**

Run (from `admin/`): `pnpm lint && pnpm typecheck`
Expected: exit 0.

```bash
git add "admin/apps/portal/app/member/(authed)/profile"
git commit -m "feat(portal): member Profile KYC section with submit dialog"
```

---

### Task 6: Operator portal — KYC submissions review queue

**Files:**
- Create: `admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/page.tsx`
- Create: `admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/_components/KycSubmissionsTable.tsx`
- Modify: `admin/apps/portal/src/components/shell/nav-config.tsx`
- Test: `admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/__tests__/KycSubmissionsTable.test.tsx`

**Interfaces:**
- Consumes: `resources.members.listKycSubmissions()` (Task 4); `KycSubmissionListItemOut` from `@sacco/schemas`; `DataTable`, `useTableUrlState`, `StatusBadge`, `FormattedDateTime` from `@sacco/ui`.
- Produces: `/members/kyc-submissions` operator route (static segment — wins over the `/members/[id]` dynamic route in Next.js).

- [ ] **Step 1: Write the failing test**

Create `admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/__tests__/KycSubmissionsTable.test.tsx`, mirroring the existing `MembersTable` test setup (URL-state provider wrapper as used by neighbouring table tests):

```tsx
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { KycSubmissionListItemOut } from "@sacco/schemas";
import { KycSubmissionsTable } from "../_components/KycSubmissionsTable";
import { renderWithProviders } from "@/test/render-with-providers";

const ROWS: KycSubmissionListItemOut[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    member_id: "m1",
    member_number: "M-00001",
    full_name: "Jane Doe",
    status: "pending",
    submitted_at: "2026-07-08T10:00:00Z",
  },
  {
    id: "22222222-2222-2222-2222-222222222222",
    member_id: "m2",
    member_number: "M-00002",
    full_name: "John Ouma",
    status: "rejected",
    submitted_at: "2026-07-07T10:00:00Z",
  },
];

describe("KycSubmissionsTable", () => {
  it("renders member numbers linking to the submission detail", () => {
    renderWithProviders(<KycSubmissionsTable rows={ROWS} />);
    const link = screen.getByRole("link", { name: "M-00001" });
    expect(link).toHaveAttribute(
      "href",
      "/members/kyc-submissions/11111111-1111-1111-1111-111111111111",
    );
  });

  it("renders submission statuses through StatusBadge", () => {
    renderWithProviders(<KycSubmissionsTable rows={ROWS} />);
    expect(screen.getByText("Pending Review")).toBeInTheDocument();
    expect(screen.getByText("Rejected")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `admin/`): `pnpm --filter @sacco/portal test -- KycSubmissionsTable`
Expected: FAIL — cannot resolve `../_components/KycSubmissionsTable`.

- [ ] **Step 3: Write the implementation**

Create `admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/_components/KycSubmissionsTable.tsx`, following `MembersTable.tsx` exactly (same `useTableUrlState` + client-side status filter + `DataTable` wiring):

```tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  DataTable,
  type DataTableProps,
  FormattedDateTime,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusBadge,
  useTableUrlState,
} from "@sacco/ui";
import type { KycSubmissionListItemOut } from "@sacco/schemas";

const STATUS_FILTER_OPTIONS = ["pending", "approved", "rejected"] as const;

const columns: DataTableProps<KycSubmissionListItemOut>["columns"] = [
  {
    id: "member_number",
    accessorKey: "member_number",
    header: "Member #",
    cell: ({ row }) => (
      <Link
        href={`/members/kyc-submissions/${row.original.id}`}
        className="font-medium text-[var(--text-link)]"
      >
        {row.original.member_number}
      </Link>
    ),
  },
  { id: "full_name", accessorKey: "full_name", header: "Member" },
  {
    id: "status",
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <StatusBadge entity="kyc_submission" status={row.original.status} />
    ),
  },
  {
    id: "submitted_at",
    accessorKey: "submitted_at",
    header: "Submitted",
    cell: ({ row }) => <FormattedDateTime value={row.original.submitted_at} />,
  },
];

function filterRows(
  rows: KycSubmissionListItemOut[],
  status: string | undefined,
): KycSubmissionListItemOut[] {
  if (!status) return rows;
  return rows.filter((r) => r.status === status);
}

export function KycSubmissionsTable({ rows }: { rows: KycSubmissionListItemOut[] }) {
  const urlState = useTableUrlState({ filterKeys: ["status"] });
  const filtered = useMemo(
    () => filterRows(rows, urlState.filters["status"]),
    [rows, urlState.filters],
  );

  return (
    <DataTable
      columns={columns}
      data={filtered}
      urlState={urlState}
      emptyState={{
        title: "No KYC submissions",
        description: "Member KYC submissions awaiting review will appear here.",
      }}
      toolbar={
        <Select
          value={urlState.filters["status"] ?? ""}
          onValueChange={(v) => urlState.setFilter("status", v || undefined)}
        >
          <SelectTrigger className="w-44" aria-label="Filter by status">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            {STATUS_FILTER_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    />
  );
}
```

(Match `useTableUrlState` / `DataTable` prop names to `MembersTable.tsx` verbatim — that file is the source of truth for filter/empty-state/toolbar wiring in this codebase; if its props differ from the sketch above, follow `MembersTable`.)

Create `admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/page.tsx`:

```tsx
import type { KycSubmissionListItemOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { KycSubmissionsTable } from "./_components/KycSubmissionsTable";

export const metadata = { title: "KYC submissions" };

export default async function KycSubmissionsPage() {
  const { resources } = await getTenantPageContext();
  const { data, error } = await (resources.members.listKycSubmissions() as Promise<{
    data?: KycSubmissionListItemOut[];
    error?: unknown;
  }>);
  if (!data) {
    throw new Error(`Failed to load KYC submissions: ${JSON.stringify(error)}`);
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">KYC submissions</h1>
      <KycSubmissionsTable rows={data} />
    </div>
  );
}
```

In `admin/apps/portal/src/components/shell/nav-config.tsx`, give the tenant `Members` item children (mirroring the `Savings` item's shape):

```tsx
      {
        label: "Members",
        href: "/members",
        icon: Users,
        children: [{ label: "KYC submissions", href: "/members/kyc-submissions" }],
      },
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `admin/`): `pnpm --filter @sacco/portal test -- KycSubmissionsTable`
Expected: PASS (2 tests). Also run the nav/sidebar tests: `pnpm --filter @sacco/portal test -- Sidebar`

- [ ] **Step 5: Checks + commit**

Run (from `admin/`): `pnpm lint && pnpm typecheck`
Expected: exit 0.

```bash
git add "admin/apps/portal/app/(tenant-authed)/members/kyc-submissions" admin/apps/portal/src/components/shell/nav-config.tsx
git commit -m "feat(portal): operator KYC submissions review queue"
```

---

### Task 7: Operator portal — submission detail (proposed-vs-current) + approve/reject

**Files:**
- Create: `admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/[id]/page.tsx`
- Create: `admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/[id]/_components/KycReviewActions.tsx`
- Test: `admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/[id]/__tests__/KycReviewActions.test.tsx`

**Interfaces:**
- Consumes: `resources.members.getKycSubmission(id)` / `approveKycSubmission(id)` / `rejectKycSubmission(id, {reason})` (Task 4); `KycSubmissionDetailOut`, `MEMBER_KYC_FIELDS` from `@sacco/schemas`; `ConfirmDialog`, `Dialog*`, `FormField`, `Textarea`, `Button`, `StatusBadge`, `toast` from `@sacco/ui`; `queryKeys.members.*`.
- Produces: `/members/kyc-submissions/[id]` operator route.

UX contract: Approve uses a plain **`ConfirmDialog`** (single-reviewer — this is NOT maker-checker, so no `MakerCheckerConfirmDialog` and no "Request X" labelling). Reject opens a small `Dialog` with a **required reason** `Textarea` (same pattern as `ApprovalActions.tsx`'s reject dialog). Both buttons render only while `status === "pending"`.

- [ ] **Step 1: Write the failing test**

Create `admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/[id]/__tests__/KycReviewActions.test.tsx`:

```tsx
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { KycReviewActions } from "../_components/KycReviewActions";
import { renderWithProviders } from "@/test/render-with-providers";

const approveKycSubmission = vi.fn().mockResolvedValue({ data: { status: "approved" } });
const rejectKycSubmission = vi.fn().mockResolvedValue({ data: { status: "rejected" } });

vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({
    resources: { members: { approveKycSubmission, rejectKycSubmission } },
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

describe("KycReviewActions", () => {
  beforeEach(() => {
    approveKycSubmission.mockClear();
    rejectKycSubmission.mockClear();
  });

  it("renders nothing when the submission is not pending", () => {
    renderWithProviders(<KycReviewActions submissionId="s1" status="approved" />);
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
  });

  it("approves after confirmation", async () => {
    const user = userEvent.setup();
    renderWithProviders(<KycReviewActions submissionId="s1" status="pending" />);
    await user.click(screen.getByRole("button", { name: /^approve$/i }));
    await user.click(screen.getByRole("button", { name: /approve submission/i }));
    await waitFor(() => expect(approveKycSubmission).toHaveBeenCalledWith("s1"));
  });

  it("requires a reason to reject", async () => {
    const user = userEvent.setup();
    renderWithProviders(<KycReviewActions submissionId="s1" status="pending" />);
    await user.click(screen.getByRole("button", { name: /^reject$/i }));
    await user.click(screen.getByRole("button", { name: /reject submission/i }));
    expect(rejectKycSubmission).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText(/reason/i), "ID number looks wrong");
    await user.click(screen.getByRole("button", { name: /reject submission/i }));
    await waitFor(() =>
      expect(rejectKycSubmission).toHaveBeenCalledWith("s1", {
        reason: "ID number looks wrong",
      }),
    );
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `admin/`): `pnpm --filter @sacco/portal test -- KycReviewActions`
Expected: FAIL — cannot resolve `../_components/KycReviewActions`.

- [ ] **Step 3: Write the implementation**

Create `admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/[id]/_components/KycReviewActions.tsx` (reject-dialog wiring copied from `ApprovalActions.tsx`):

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Button,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  FormField,
  Textarea,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

const rejectSchema = z.object({
  reason: z.string().trim().min(3, "Give the member a reason they can act on"),
});
type RejectInput = z.infer<typeof rejectSchema>;

export function KycReviewActions({
  submissionId,
  status,
}: {
  submissionId: string;
  status: string;
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);

  const invalidates = [
    queryKeys.members.kycSubmissions(),
    queryKeys.members.kycSubmission(submissionId),
    queryKeys.members.root(),
  ];

  const rejectForm = useForm<RejectInput>({
    resolver: zodResolver(rejectSchema),
    defaultValues: { reason: "" },
  });

  const approveMutation = useTypedMutation<unknown, void>(
    async () => {
      const res = await (resources.members.approveKycSubmission(
        submissionId,
      ) as Promise<{ data?: unknown; error?: unknown }>);
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("KYC approved", {
          description: "The proposed details were applied to the member record.",
        });
        setApproveOpen(false);
        router.refresh();
      },
      onError: (error) =>
        toast.error("The submission was not approved", {
          description: apiErrorMessage(error, "Please try again."),
        }),
    },
  );

  const rejectMutation = useTypedMutation<unknown, RejectInput>(
    async (vars) => {
      const res = await (resources.members.rejectKycSubmission(submissionId, {
        reason: vars.reason,
      }) as Promise<{ data?: unknown; error?: unknown }>);
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("KYC rejected", {
          description: "The member can see the reason and resubmit.",
        });
        setRejectOpen(false);
        rejectForm.reset();
        router.refresh();
      },
      onError: (error) =>
        toast.error("The submission was not rejected", {
          description: apiErrorMessage(error, "Please try again."),
        }),
    },
  );

  if (status !== "pending") return null;

  return (
    <div className="flex gap-3">
      <Button onClick={() => setApproveOpen(true)}>Approve</Button>
      <Button variant="destructive" onClick={() => setRejectOpen(true)}>
        Reject
      </Button>

      <ConfirmDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        title="Approve KYC submission?"
        description="The proposed details will be written to the member record. Member status is not changed — activation stays a separate approval flow."
        confirmLabel="Approve submission"
        busy={approveMutation.isPending}
        onConfirm={() => approveMutation.mutate()}
      />

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject KYC submission</DialogTitle>
            <DialogDescription>
              The reason is shown to the member so they can fix and resubmit.
            </DialogDescription>
          </DialogHeader>
          <form
            onSubmit={rejectForm.handleSubmit((vars) => rejectMutation.mutate(vars))}
            className="space-y-4"
          >
            <FormField
              control={rejectForm.control}
              name="reason"
              label="Reason"
              render={({ field }) => <Textarea rows={3} {...field} />}
            />
            <div className="flex justify-end gap-3">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setRejectOpen(false)}
                disabled={rejectMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="destructive"
                disabled={rejectMutation.isPending}
              >
                Reject submission
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
```

Create `admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/[id]/page.tsx`:

```tsx
import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, FormattedDateTime, StatusBadge } from "@sacco/ui";
import { MEMBER_KYC_FIELDS, type KycSubmissionDetailOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { KycReviewActions } from "./_components/KycReviewActions";

export const metadata = { title: "KYC submission" };

export default async function KycSubmissionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getTenantPageContext();
  const { data, error } = await (resources.members.getKycSubmission(id) as Promise<{
    data?: KycSubmissionDetailOut;
    error?: unknown;
  }>);
  if (!data) {
    if ((error as { status?: number } | undefined)?.status === 404) notFound();
    throw new Error(`Failed to load KYC submission: ${JSON.stringify(error)}`);
  }

  const { submission, current } = data;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-[var(--text-h3)] font-semibold">
            KYC submission — {data.full_name}
          </h1>
          <p className="text-[var(--text-secondary)]">
            <Link
              href={`/members/${submission.member_id}`}
              className="text-[var(--text-link)]"
            >
              {data.member_number}
            </Link>{" "}
            · Submitted <FormattedDateTime value={submission.submitted_at} />
          </p>
        </div>
        <StatusBadge entity="kyc_submission" status={submission.status} />
      </div>

      {submission.status === "rejected" && submission.rejection_reason ? (
        <Card className="p-4">
          <p className="font-medium">Rejection reason</p>
          <p className="text-[var(--text-secondary)]">{submission.rejection_reason}</p>
        </Card>
      ) : null}

      <Card className="overflow-x-auto p-0">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-[var(--border-default)]">
              <th className="p-3 font-medium">Field</th>
              <th className="p-3 font-medium">Current</th>
              <th className="p-3 font-medium">Proposed</th>
            </tr>
          </thead>
          <tbody>
            {MEMBER_KYC_FIELDS.map((field) => {
              const before = current[field.key];
              const after = submission.proposed[field.key];
              const changed = before !== after;
              return (
                <tr key={field.key} className="border-b border-[var(--border-default)] last:border-0">
                  <td className="p-3 text-[var(--text-secondary)]">{field.label}</td>
                  <td className="p-3">{before ?? "—"}</td>
                  <td className={changed ? "p-3 font-medium" : "p-3"}>
                    {after ?? "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      <KycReviewActions submissionId={submission.id} status={submission.status} />
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (from `admin/`): `pnpm --filter @sacco/portal test -- KycReviewActions`
Expected: PASS (3 tests).

- [ ] **Step 5: Checks + commit**

Run (from `admin/`): `pnpm lint && pnpm typecheck`
Expected: exit 0.

```bash
git add "admin/apps/portal/app/(tenant-authed)/members/kyc-submissions/[id]"
git commit -m "feat(portal): KYC submission detail with proposed-vs-current + approve/reject"
```

---

### Task 8: Close-out — full suites + CLAUDE.md member-write contract

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Backend suite**

Run: `python -m ruff check app/ tests/ && python -m mypy app/ && python -m pytest tests/core/ tests/modules/members/ tests/modules/organization/ tests/platform_/kyc/ -q`
Expected: all clean/green.

- [ ] **Step 2: Admin suite**

Run (from `admin/`): `pnpm lint && pnpm typecheck && pnpm test`
Expected: all exit 0.

- [ ] **Step 3: Update the CLAUDE.md contracts**

(a) In "## Member auth contracts (Phase 4a — do not violate)", replace the sentence
"Members are **read-only** in v1 — no member mutations, no member-side maker-checker."
(inside the `/member/*` read-endpoints bullet) with:

```markdown
  Cross-member access returns **404**, never 403. Members may write **only** a
  KYC submission (`POST /member/me/kyc`) — no other member mutations, no
  member-side maker-checker.
```

(b) In "## KYC tracking contracts (do not violate)", insert a new bullet after the existing "**Member KYC:**" bullet:

```markdown
- **Member KYC submissions:** `kyc_submissions` (tenant schema) holds proposed-field
  snapshots of the 11 non-locked catalog keys. `MemberSelfService.submit_kyc` is the
  only submit path: at most one `pending` row per member (partial unique index);
  resubmission supersedes the open pending row IN PLACE; reviewed rows are terminal
  history and never deleted. `KycReviewService.approve` is the ONLY path that applies
  KYC fields to the member row (full snapshot replace, audited via AuditableMixin);
  it never touches member status — activation stays maker-checker. Review is
  single-reviewer, NOT maker-checker. Uniqueness (`national_id_number`, `email`) is
  enforced at approve time (409), never at submit. Operator surface:
  `GET /members/kyc-submissions[?status=]`, `GET/POST .../{id}[/approve|/reject]`
  (reject requires a reason) — registered BEFORE the `/{member_id}` route.
```

(c) In the same section's "**Member KYC:**" bullet, delete the now-false sentence
"The increment-5 columns (`next_of_kin_name`, `next_of_kin_phone`, `occupation`) read as absent until they ship."

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): member KYC submission/review contract (increment 5)"
```

---

## Out of scope for this plan

- Member loan apply (`POST /member/loan-applications`) and the consolidated member
  statement — increments 2 and 4 of the 2026-06-29 member self-service design,
  planned separately.
- KYC document/photo uploads, object storage, async statement generation.
- Extending the member portal beyond the Profile KYC section (no new nav items on
  the member side).
- Explicit audit rows for requirement-toggle writes and the deferred increment-3
  minors (whitespace-email Zod edge, onError/unverify test gaps) — still a separate
  follow-up.
- Notifications on approve/reject (Phase 3 dependency).
