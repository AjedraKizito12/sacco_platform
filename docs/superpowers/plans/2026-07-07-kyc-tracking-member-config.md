# KYC Tracking Increment 4 — Member Required-Set Config + Tracker Surfacing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-tenant member KYC required-set config (`member_kyc_requirements` + operator endpoints/page) and member completion surfaced on the operator member detail and `GET /member/me/kyc`.

**Architecture:** Backend first: a tenant-schema override table mirroring the merged `platform.sacco_kyc_requirements`, a `MemberKycRequirementsService` + completion helper in the members module (computing against `MEMBER_KYC_CATALOG` via the pure `app/core/kyc` tracker), Pydantic requirement/completion schemas hoisted into `app/core/kyc/schemas.py` (org/platform modules re-export), and four endpoints. Then portal: TS types + resources, a shared requirements-toggles component (refactoring the platform SACCO form to use it), the operator "Member KYC requirements" page, and a `KycCompletionCard` on the member detail.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic (tenant schema), pytest with the repo's per-phase fresh-session `factory` fixture; Next.js 15 portal, `@sacco/*` packages, Vitest.

**Spec:** `docs/superpowers/specs/2026-06-30-kyc-fulfilment-tracking-design.md` (§3 Member KYC, §API surface, §Portal design, build-sequence increment 4).

## Global Constraints

- Tenant model tables declare NO schema (resolved via `search_path`). Migration goes in `alembic/tenant/versions/` as revision `017`, `down_revision = "016"`.
- `compute_completion` (in `app/core/kyc/completion.py`) is the ONLY completion computation (CLAUDE.md KYC contract). `app/core/kyc/` stays pure — no DB, no I/O, no imports from `app/modules` or `app/platform_` (Pydantic schemas are fine).
- **The three increment-5 member columns do not exist yet** (`next_of_kin_name`, `next_of_kin_phone`, `occupation` — per the spec they ship with the submission flow). The values mapping uses `getattr(member, key, None)` so they read as absent. Members will show them as missing while they're default-required; that is correct informational behaviour (data not collected yet), and tenants can toggle them off. Do NOT add these columns in this increment.
- **Route ordering:** `/members/kyc-requirements` MUST be registered BEFORE `/members/{member_id}` in `app/modules/members/api.py` — `member_id` is UUID-typed, so a later literal segment would 422 instead of matching. A regression test enforces this.
- Response narrowing (documented deviations from the spec's response listings, both extend cleanly in increment 5):
  - `GET /members/{member_id}/kyc` returns `{ member_id, completion }` — the member's raw values are already served by `GET /members/{member_id}` and the operator detail page renders them; duplicating them here adds nothing.
  - `GET /member/me/kyc` returns `{ completion }` — values come from `GET /member/me`; "latest submission status" arrives with increment 5's `kyc_submissions`.
- Requirement-toggle writes carry no explicit audit rows — this mirrors the merged `sacco_kyc_requirements` implementation (increments 1–2, PR #57). Known deviation from the spec's audit section, deferred deliberately; if it's ever fixed, fix both tables together.
- Operator endpoints gate on `CurrentTenantUser`; member endpoint on `CurrentMember` (both via `get_tenant_session`, subscription-gated). Cross-member access is impossible by construction (`/member/me/kyc` uses `current_member` only).
- Portal contracts: no client-side initial fetch (contract M); colors via `var(--...)` tokens; toggles UI mirrors the merged SACCO settings page; existing platform SACCO form tests must stay green through the shared-component refactor.
- Backend commands run from `/home/liam/projects/sacco-platform`; pnpm commands from `/home/liam/projects/sacco-platform/admin`.
- Backend tests need the dockerized `postgres-test` on :5433 (`docker compose up -d postgres-test` if not running).

## Prerequisites

1. Branch off current `main` (which includes PRs #57, #58, #60): `git checkout -b feat/kyc-member-config main`.
2. Confirm `admin/apps/portal/src/components/shell/nav-config.tsx` and `admin/apps/portal/src/components/kyc/KycCompletionCard.tsx` exist (increment 3, merged).

## File Structure

```
app/modules/members/models.py                       (modify — add MemberKycRequirement)
alembic/tenant/versions/017_member_kyc_requirements.py (new)
app/modules/members/kyc.py                          (new — requirements service + completion helper)
app/core/kyc/schemas.py                             (new — hoisted KYC Pydantic schemas)
app/modules/organization/schemas.py                 (modify — import completion schemas from core)
app/platform_/kyc/schemas.py                        (modify — alias requirement schemas from core)
app/modules/members/schemas.py                      (modify — MemberKycOut, MemberSelfKycOut)
app/modules/members/api.py                          (modify — 3 operator routes + 1 member route)
tests/modules/members/test_kyc_requirements.py      (new — model + service + completion)
tests/modules/members/test_kyc_api.py               (new — endpoint tests incl. route-order regression)
admin/packages/schemas/src/kyc.ts                   (modify — member KYC TS types)
admin/packages/api-client/src/resources/members.ts  (modify — 3 methods)
admin/packages/api-client/src/resources/member.ts   (modify — getMyKyc)
admin/packages/api-client/src/query-keys.ts         (modify — members.kycRequirements/kyc, member.kyc)
admin/packages/api-client/src/__tests__/query-keys-member-kyc.test.ts (new)
admin/apps/portal/src/components/kyc/KycRequirementsToggles.tsx (new — shared presentational toggles)
admin/apps/portal/app/platform/(authed)/settings/kyc/_components/SaccoKycRequirementsForm.tsx (modify — consume shared toggles)
admin/apps/portal/app/(tenant-authed)/organization/member-kyc-requirements/page.tsx (new)
admin/apps/portal/app/(tenant-authed)/organization/member-kyc-requirements/_components/MemberKycRequirementsForm.tsx (new)
admin/apps/portal/app/(tenant-authed)/organization/member-kyc-requirements/__tests__/MemberKycRequirementsForm.test.tsx (new)
admin/apps/portal/app/(tenant-authed)/members/[id]/page.tsx (modify — completion card)
admin/apps/portal/src/components/shell/nav-config.tsx (modify — Organization group second item)
CLAUDE.md                                            (modify — member-KYC contract bullet, close-out)
```

---

### Task 1: `member_kyc_requirements` tenant model + migration 017

**Files:**
- Modify: `app/modules/members/models.py` (append class at end of file)
- Create: `alembic/tenant/versions/017_member_kyc_requirements.py`
- Test: `tests/modules/members/test_kyc_requirements.py` (model section)

**Interfaces:**
- Consumes: `Base` from `app.core.db` (already imported in models.py).
- Produces: `MemberKycRequirement` with `field_key: str` (PK) and `is_required: bool` — consumed by Task 2's service.

- [ ] **Step 1: Write the failing test**

Create `tests/modules/members/test_kyc_requirements.py`:

```python
"""Member KYC requirements: model roundtrip, service, completion helper."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.members.models import Member, MemberKycRequirement

SCHEMA = "tenant_test"


async def _set_path(s: AsyncSession) -> None:
    await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))


@pytest.fixture
async def factory(test_engine: AsyncEngine) -> AsyncGenerator[async_sessionmaker, None]:
    maker = async_sessionmaker(test_engine, expire_on_commit=False)
    yield maker
    async with maker() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text("DELETE FROM member_kyc_requirements"))
        await s.execute(text("DELETE FROM audit_log WHERE table_name = 'members'"))
        await s.execute(text("DELETE FROM members"))
        await s.commit()


async def test_member_kyc_requirement_roundtrip(factory: async_sessionmaker) -> None:
    async with factory() as s:
        await _set_path(s)
        s.add(MemberKycRequirement(field_key="occupation", is_required=True))
        await s.commit()
    async with factory() as s:
        await _set_path(s)
        row = (
            await s.execute(
                select(MemberKycRequirement).where(
                    MemberKycRequirement.field_key == "occupation"
                )
            )
        ).scalar_one()
    assert row.is_required is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/modules/members/test_kyc_requirements.py -q`
Expected: FAIL — `ImportError: cannot import name 'MemberKycRequirement'`.

- [ ] **Step 3: Write the implementation**

Append to `app/modules/members/models.py` (after the `Member` class; `Boolean`, `Text`, `Mapped`, `mapped_column`, `Base` are already imported):

```python
class MemberKycRequirement(Base):
    """Per-tenant override of a member KYC field's required-ness.

    Override rows only: a missing row means "use the catalog default".
    Locked catalog fields ignore any row here. One row per field_key.
    Tenant-schema twin of platform.sacco_kyc_requirements.
    """

    __tablename__ = "member_kyc_requirements"

    field_key: Mapped[str] = mapped_column(Text, primary_key=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
```

Create `alembic/tenant/versions/017_member_kyc_requirements.py`:

```python
"""Per-tenant member KYC required-set overrides.

Revision: 017
Depends on: 016
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "member_kyc_requirements",
        sa.Column("field_key", sa.Text(), primary_key=True),
        sa.Column("is_required", sa.Boolean(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("member_kyc_requirements")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/modules/members/test_kyc_requirements.py -q`
Expected: PASS (1 test). (The test harness migrates `tenant_test` to head, picking up 017.)

- [ ] **Step 5: Lint, typecheck, commit**

Run: `python -m ruff check app/ tests/ && python -m mypy app/`
Expected: clean.

```bash
git add app/modules/members/models.py alembic/tenant/versions/017_member_kyc_requirements.py tests/modules/members/test_kyc_requirements.py
git commit -m "feat(members): member_kyc_requirements table for per-tenant KYC required-set"
```

---

### Task 2: `MemberKycRequirementsService` + completion helper

**Files:**
- Create: `app/modules/members/kyc.py`
- Test: `tests/modules/members/test_kyc_requirements.py` (append service/completion tests)

**Interfaces:**
- Consumes: `MEMBER_KYC_CATALOG`, `FieldSpec` from `app.core.kyc.catalog`; `compute_completion`, `KycCompletion` from `app.core.kyc.completion`; Task 1's `MemberKycRequirement`; `Member` model.
- Produces (used by Task 4's endpoints):
  - `MemberKycRequirementsService(session)` with `async effective_required() -> dict[str, bool]`, `async list_config() -> list[tuple[FieldSpec, bool]]`, `async replace(overrides: Mapping[str, bool]) -> None`
  - `member_kyc_values(member: Member) -> dict[str, object | None]`
  - `async member_kyc_completion(session: AsyncSession, member: Member) -> KycCompletion`

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/members/test_kyc_requirements.py`:

```python
async def _make_member(s: AsyncSession, **overrides: object) -> Member:
    member = Member(
        member_number=f"M-{uuid.uuid4().hex[:6]}",
        full_name="Jane Member",
        date_of_birth=date(1990, 5, 15),
        gender="female",
        **overrides,
    )
    s.add(member)
    await s.flush()
    return member


async def test_locked_keys_always_required_and_replace_ignores_them(
    factory: async_sessionmaker,
) -> None:
    from app.modules.members.kyc import MemberKycRequirementsService

    async with factory() as s:
        await _set_path(s)
        svc = MemberKycRequirementsService(s)
        # attempt to disable a locked key and an unknown key; toggle a real one off
        await svc.replace({"full_name": False, "nonsense": True, "phone": False})
        await s.commit()

    async with factory() as s:
        await _set_path(s)
        eff = await MemberKycRequirementsService(s).effective_required()
    assert eff["full_name"] is True  # locked — override ignored
    assert "nonsense" not in eff  # unknown — dropped
    assert eff["phone"] is False  # toggleable — respected
    assert eff["occupation"] is False  # catalog default_required=False


async def test_completion_counts_missing_and_absent_increment5_columns(
    factory: async_sessionmaker,
) -> None:
    from app.modules.members.kyc import member_kyc_completion

    async with factory() as s:
        await _set_path(s)
        member = await _make_member(s, phone="+256700000001")
        completion = await member_kyc_completion(s, member)
        await s.commit()

    by_key = {item.key: item for item in completion.items}
    assert by_key["full_name"].present is True  # locked NOT NULL column
    assert by_key["phone"].present is True
    assert by_key["email"].present is False
    # increment-5 columns don't exist on the model yet → absent, not an error
    assert by_key["next_of_kin_name"].present is False
    assert completion.is_complete is False
    assert "next_of_kin_name" in completion.missing_required


async def test_toggling_off_all_missing_makes_member_complete(
    factory: async_sessionmaker,
) -> None:
    from app.modules.members.kyc import (
        MemberKycRequirementsService,
        member_kyc_completion,
    )

    async with factory() as s:
        await _set_path(s)
        member = await _make_member(
            s,
            phone="+256700000002",
            email=f"jane-{uuid.uuid4().hex[:6]}@example.com",
            physical_address="1 Kampala Rd",
            national_id_number=f"CF{uuid.uuid4().hex[:8].upper()}",
            id_document_type="national_id",
            id_document_number="DOC-1",
        )
        # everything still missing is not collectable yet — toggle it off
        await MemberKycRequirementsService(s).replace(
            {"next_of_kin_name": False, "next_of_kin_phone": False}
        )
        completion = await member_kyc_completion(s, member)
        await s.commit()

    assert completion.is_complete is True
    assert completion.percent == 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/modules/members/test_kyc_requirements.py -q`
Expected: 1 pass (Task 1), 3 FAIL — `ModuleNotFoundError: No module named 'app.modules.members.kyc'`.

- [ ] **Step 3: Write the implementation**

Create `app/modules/members/kyc.py`:

```python
"""Member KYC: per-tenant required-set service + completion helper.

Tenant-schema twin of app/platform_/kyc/service.py (which owns the
platform-global SACCO required set). Completion always goes through
app.core.kyc.compute_completion — never hand-rolled.
"""
from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kyc.catalog import MEMBER_KYC_CATALOG, FieldSpec
from app.core.kyc.completion import KycCompletion, compute_completion
from app.modules.members.models import Member, MemberKycRequirement

_TOGGLEABLE = {f.key for f in MEMBER_KYC_CATALOG if not f.locked}
_VALUE_KEYS: tuple[str, ...] = tuple(f.key for f in MEMBER_KYC_CATALOG)


class MemberKycRequirementsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _overrides(self) -> dict[str, bool]:
        rows = (
            await self._session.execute(select(MemberKycRequirement))
        ).scalars().all()
        return {r.field_key: r.is_required for r in rows}

    async def effective_required(self) -> dict[str, bool]:
        overrides = await self._overrides()
        result: dict[str, bool] = {}
        for spec in MEMBER_KYC_CATALOG:
            if spec.locked:
                result[spec.key] = True
            else:
                result[spec.key] = overrides.get(spec.key, spec.default_required)
        return result

    async def list_config(self) -> list[tuple[FieldSpec, bool]]:
        eff = await self.effective_required()
        return [(spec, eff[spec.key]) for spec in MEMBER_KYC_CATALOG]

    async def replace(self, overrides: Mapping[str, bool]) -> None:
        """Replace all override rows. Locked and unknown keys are ignored;
        only non-locked catalog keys are persisted."""
        await self._session.execute(delete(MemberKycRequirement))
        for key, required in overrides.items():
            if key in _TOGGLEABLE:
                self._session.add(
                    MemberKycRequirement(field_key=key, is_required=bool(required))
                )
        await self._session.flush()


def member_kyc_values(member: Member) -> dict[str, object | None]:
    """Catalog-keyed values for one member.

    getattr default handles catalog keys whose columns ship with increment 5
    (next_of_kin_name, next_of_kin_phone, occupation) — absent column reads
    as "not provided", which is the truth until the data can be collected.
    """
    return {key: getattr(member, key, None) for key in _VALUE_KEYS}


async def member_kyc_completion(
    session: AsyncSession, member: Member
) -> KycCompletion:
    overrides = await MemberKycRequirementsService(session).effective_required()
    return compute_completion(member_kyc_values(member), MEMBER_KYC_CATALOG, overrides)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/modules/members/test_kyc_requirements.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint, typecheck, commit**

Run: `python -m ruff check app/ tests/ && python -m mypy app/`
Expected: clean.

```bash
git add app/modules/members/kyc.py tests/modules/members/test_kyc_requirements.py
git commit -m "feat(members): MemberKycRequirementsService + member completion helper"
```

---

### Task 3: Hoist KYC Pydantic schemas to core; add member KYC schemas

**Files:**
- Create: `app/core/kyc/schemas.py`
- Modify: `app/modules/organization/schemas.py` (delete local `KycFieldStatusOut`/`KycCompletionOut` classes; import from core instead)
- Modify: `app/platform_/kyc/schemas.py` (replace local classes with core aliases)
- Modify: `app/modules/members/schemas.py` (add `MemberKycOut`, `MemberSelfKycOut`)
- Test: `tests/core/test_kyc_schemas.py` (new)

**Interfaces:**
- Consumes: `FieldSpec` from `app.core.kyc.catalog`, `KycCompletion` from `app.core.kyc.completion`.
- Produces (used by Task 4):
  - `app.core.kyc.schemas`: `KycFieldStatusOut`, `KycCompletionOut` (with `from_completion(c: KycCompletion) -> KycCompletionOut`), `KycRequirementItemOut`, `KycRequirementsOut` (with `from_config(config: list[tuple[FieldSpec, bool]]) -> KycRequirementsOut`), `KycRequirementsIn` (`required: dict[str, bool]`)
  - `app.modules.members.schemas`: `MemberKycOut { member_id: UUID, completion: KycCompletionOut }`, `MemberSelfKycOut { completion: KycCompletionOut }`
  - Existing public names keep working: `app.modules.organization.schemas.KycCompletionOut` / `.KycFieldStatusOut` (re-exported), `app.platform_.kyc.schemas.SaccoKycRequirement{ItemOut,sOut,sIn}` (aliases). Wire shapes are unchanged.

- [ ] **Step 1: Write the failing test**

Create `tests/core/test_kyc_schemas.py`:

```python
from __future__ import annotations

from app.core.kyc.catalog import MEMBER_KYC_CATALOG
from app.core.kyc.completion import compute_completion
from app.core.kyc.schemas import KycCompletionOut, KycRequirementsIn, KycRequirementsOut


def test_completion_out_mirrors_computation() -> None:
    completion = compute_completion(
        {spec.key: None for spec in MEMBER_KYC_CATALOG},
        MEMBER_KYC_CATALOG,
        {},
    )
    out = KycCompletionOut.from_completion(completion)
    assert out.required_total == completion.required_total
    assert out.is_complete is False
    assert len(out.items) == len(MEMBER_KYC_CATALOG)


def test_requirements_out_from_config_preserves_order_and_locks() -> None:
    config = [(spec, spec.locked or spec.default_required) for spec in MEMBER_KYC_CATALOG]
    out = KycRequirementsOut.from_config(config)
    assert [i.key for i in out.items] == [s.key for s in MEMBER_KYC_CATALOG]
    assert out.items[0].locked is True  # full_name


def test_requirements_in_shape() -> None:
    body = KycRequirementsIn(required={"phone": False})
    assert body.required == {"phone": False}


def test_backcompat_reexports() -> None:
    # Existing import sites must keep working after the hoist.
    from app.modules.organization.schemas import KycCompletionOut as OrgAlias
    from app.platform_.kyc.schemas import SaccoKycRequirementsOut

    assert OrgAlias is KycCompletionOut
    assert SaccoKycRequirementsOut is KycRequirementsOut
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/core/test_kyc_schemas.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.kyc.schemas'`.

- [ ] **Step 3: Write the implementation**

Create `app/core/kyc/schemas.py`:

```python
"""Shared KYC wire schemas (pure — no DB, no I/O, per the core-tracker contract).

Consumed by the organization module (SACCO org KYC), platform_ KYC config,
and the members module (member KYC). Entity-specific response envelopes
stay in their modules; the completion/requirements shapes live here once.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.core.kyc.catalog import FieldSpec
from app.core.kyc.completion import KycCompletion


class KycFieldStatusOut(BaseModel):
    key: str
    label: str
    required: bool
    present: bool


class KycCompletionOut(BaseModel):
    items: list[KycFieldStatusOut]
    required_total: int
    required_present: int
    percent: int
    missing_required: list[str]
    is_complete: bool

    @classmethod
    def from_completion(cls, c: KycCompletion) -> KycCompletionOut:
        return cls(
            items=[
                KycFieldStatusOut(
                    key=i.key, label=i.label, required=i.required, present=i.present
                )
                for i in c.items
            ],
            required_total=c.required_total,
            required_present=c.required_present,
            percent=c.percent,
            missing_required=list(c.missing_required),
            is_complete=c.is_complete,
        )


class KycRequirementItemOut(BaseModel):
    key: str
    label: str
    locked: bool
    required: bool


class KycRequirementsOut(BaseModel):
    items: list[KycRequirementItemOut]

    @classmethod
    def from_config(cls, config: list[tuple[FieldSpec, bool]]) -> KycRequirementsOut:
        return cls(
            items=[
                KycRequirementItemOut(
                    key=spec.key, label=spec.label, locked=spec.locked, required=required
                )
                for spec, required in config
            ]
        )


class KycRequirementsIn(BaseModel):
    """Map of field_key → required. Locked/unknown keys are ignored server-side."""

    required: dict[str, bool]
```

Modify `app/modules/organization/schemas.py`: delete the local `KycFieldStatusOut` and `KycCompletionOut` class definitions (and the now-unused `from app.core.kyc.completion import KycCompletion` import if nothing else uses it) and add at the top:

```python
from app.core.kyc.schemas import KycCompletionOut, KycFieldStatusOut

__all__ = [
    "KycCompletionOut",
    "KycFieldStatusOut",
    "OrganizationKycOut",
    "OrganizationKycValuesIn",
    "OrganizationKycValuesOut",
]
```

(`OrganizationKycOut.from_row_and_completion` keeps calling `KycCompletionOut.from_completion(...)` — now the core class. Everything else in the file is unchanged.)

Modify `app/platform_/kyc/schemas.py` — replace the entire file body with:

```python
from __future__ import annotations

from app.core.kyc.schemas import (
    KycRequirementItemOut,
    KycRequirementsIn,
    KycRequirementsOut,
)

# Back-compat names used by app/platform_/kyc/api.py and its tests.
# Same classes, same wire shapes — the definitions moved to app.core.kyc.schemas
# so the members module can reuse them without cross-module imports.
SaccoKycRequirementItemOut = KycRequirementItemOut
SaccoKycRequirementsOut = KycRequirementsOut
SaccoKycRequirementsIn = KycRequirementsIn

__all__ = [
    "SaccoKycRequirementItemOut",
    "SaccoKycRequirementsIn",
    "SaccoKycRequirementsOut",
]
```

Modify `app/modules/members/schemas.py` — add (with the existing imports; add `from app.core.kyc.schemas import KycCompletionOut` and `import uuid` if not present):

```python
class MemberKycOut(BaseModel):
    """Operator view: one member's KYC completion (values come from GET /members/{id})."""

    member_id: uuid.UUID
    completion: KycCompletionOut


class MemberSelfKycOut(BaseModel):
    """Member self view. Increment 5 adds latest-submission status here."""

    completion: KycCompletionOut
```

- [ ] **Step 4: Run tests to verify they pass — including the untouched increment 1–2 suites**

Run: `python -m pytest tests/core/test_kyc_schemas.py tests/modules/organization/ tests/platform_/kyc/ -q`
Expected: ALL PASS (the org + platform KYC suites prove the hoist broke nothing).

- [ ] **Step 5: Lint, typecheck, commit**

Run: `python -m ruff check app/ tests/ && python -m mypy app/`
Expected: clean.

```bash
git add app/core/kyc/schemas.py app/modules/organization/schemas.py app/platform_/kyc/schemas.py app/modules/members/schemas.py tests/core/test_kyc_schemas.py
git commit -m "refactor(kyc): hoist completion/requirements schemas to app/core/kyc; member KYC envelopes"
```

---

### Task 4: Members module KYC endpoints (operator + member)

**Files:**
- Modify: `app/modules/members/api.py`
- Test: `tests/modules/members/test_kyc_api.py` (new)

**Interfaces:**
- Consumes: Task 2's `MemberKycRequirementsService`, `member_kyc_completion`; Task 3's `KycRequirementsOut/In`, `KycCompletionOut`, `MemberKycOut`, `MemberSelfKycOut`; existing `MemberService.get_member` (raises `ValueError` → 404, same as the existing `get_member` handler); existing `Session`, `CurrentTenantUser`, `CurrentMember` annotations in api.py.
- Produces: `GET/PUT /members/kyc-requirements`, `GET /members/{member_id}/kyc`, `GET /member/me/kyc` — the exact paths Task 5's portal resources target.

- [ ] **Step 1: Write the failing tests**

Create `tests/modules/members/test_kyc_api.py`:

```python
"""HTTP tests: member KYC requirements config + completion endpoints."""
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
        await s.execute(text("DELETE FROM member_kyc_requirements"))
        await s.execute(text("DELETE FROM member_sessions"))
        await s.execute(text("DELETE FROM audit_log WHERE table_name = 'members'"))
        await s.execute(text("DELETE FROM members"))
        await s.commit()


async def _create_member(client: AsyncClient) -> dict[str, Any]:
    resp = await client.post(
        "/members",
        json={
            "full_name": f"Member {uuid.uuid4().hex[:6]}",
            "date_of_birth": "1990-05-15",
            "gender": "female",
            "email": f"m-{uuid.uuid4().hex[:6]}@example.com",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_get_requirements_not_shadowed_by_member_id_route(
    client: AsyncClient,
) -> None:
    # Regression: /members/kyc-requirements must be registered before
    # /members/{member_id} or this returns 422 (UUID parse failure).
    resp = await client.get("/members/kyc-requirements", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 14
    by_key = {i["key"]: i for i in items}
    assert by_key["full_name"]["locked"] is True
    assert by_key["occupation"]["required"] is False  # default_required=False


async def test_put_requirements_replaces_and_ignores_locked(
    client: AsyncClient,
) -> None:
    resp = await client.put(
        "/members/kyc-requirements",
        json={"required": {"full_name": False, "phone": False, "occupation": True}},
        headers=HEADERS,
    )
    assert resp.status_code == 200, resp.text
    by_key = {i["key"]: i for i in resp.json()["items"]}
    assert by_key["full_name"]["required"] is True  # locked ignored
    assert by_key["phone"]["required"] is False
    assert by_key["occupation"]["required"] is True


async def test_member_kyc_completion_endpoint(client: AsyncClient) -> None:
    member = await _create_member(client)
    resp = await client.get(f"/members/{member['id']}/kyc", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["member_id"] == member["id"]
    assert body["completion"]["is_complete"] is False
    assert body["completion"]["required_total"] > 0


async def test_member_kyc_unknown_member_404(client: AsyncClient) -> None:
    resp = await client.get(f"/members/{uuid.uuid4()}/kyc", headers=HEADERS)
    assert resp.status_code == 404


async def test_member_me_kyc(client: AsyncClient, test_engine: AsyncEngine) -> None:
    member = await _create_member(client)
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

    resp = await client.get(
        "/member/me/kyc", headers={**HEADERS, "X-Member-Actor-ID": member["id"]}
    )
    assert resp.status_code == 200, resp.text
    completion = resp.json()["completion"]
    assert completion["is_complete"] is False
    assert any(i["key"] == "next_of_kin_name" for i in completion["items"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/modules/members/test_kyc_api.py -q`
Expected: FAIL — 404s/422s (routes don't exist yet).

- [ ] **Step 3: Write the implementation**

Modify `app/modules/members/api.py`:

Add imports (merge into existing import block):

```python
from app.core.kyc.schemas import KycCompletionOut, KycRequirementsIn, KycRequirementsOut
from app.modules.members.kyc import MemberKycRequirementsService, member_kyc_completion
from app.modules.members.schemas import MemberKycOut, MemberSelfKycOut
```

Insert the two requirements handlers **immediately after the `list_members` handler and BEFORE the `get_member` (`/{member_id}`) handler** — the literal path must register first:

```python
@router.get("/kyc-requirements", response_model=KycRequirementsOut)
async def get_member_kyc_requirements(
    session: Session, _user: CurrentTenantUser
) -> KycRequirementsOut:
    # NOTE: registered before /{member_id} — a UUID-typed path param would
    # otherwise swallow this literal segment and 422.
    config = await MemberKycRequirementsService(session).list_config()
    return KycRequirementsOut.from_config(config)


@router.put("/kyc-requirements", response_model=KycRequirementsOut)
async def put_member_kyc_requirements(
    body: KycRequirementsIn, session: Session, _user: CurrentTenantUser
) -> KycRequirementsOut:
    svc = MemberKycRequirementsService(session)
    await svc.replace(body.required)
    return KycRequirementsOut.from_config(await svc.list_config())
```

Insert after the existing `get_member` handler:

```python
@router.get("/{member_id}/kyc", response_model=MemberKycOut)
async def get_member_kyc(
    member_id: uuid.UUID, session: Session, _user: CurrentTenantUser
) -> MemberKycOut:
    svc = MemberService(session)
    try:
        member = await svc.get_member(member_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    completion = await member_kyc_completion(session, member)
    return MemberKycOut(
        member_id=member.id, completion=KycCompletionOut.from_completion(completion)
    )
```

Insert after the existing `member_self` handler on `member_router`:

```python
@member_router.get("/me/kyc", response_model=MemberSelfKycOut)
async def member_self_kyc(member: CurrentMember, session: Session) -> MemberSelfKycOut:
    completion = await member_kyc_completion(session, member)
    return MemberSelfKycOut(completion=KycCompletionOut.from_completion(completion))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/modules/members/test_kyc_api.py tests/modules/members/ -q`
Expected: ALL PASS (new + existing members suites).

- [ ] **Step 5: Lint, typecheck, commit**

Run: `python -m ruff check app/ tests/ && python -m mypy app/`
Expected: clean.

```bash
git add app/modules/members/api.py tests/modules/members/test_kyc_api.py
git commit -m "feat(members): KYC requirements + completion endpoints (operator + member)"
```

---

### Task 5: Portal TS types, resources, query keys

**Files:**
- Modify: `admin/packages/schemas/src/kyc.ts` (append)
- Modify: `admin/packages/api-client/src/resources/members.ts`
- Modify: `admin/packages/api-client/src/resources/member.ts`
- Modify: `admin/packages/api-client/src/query-keys.ts`
- Test: `admin/packages/api-client/src/__tests__/query-keys-member-kyc.test.ts` (new)

**Interfaces:**
- Consumes: existing `SaccoKycRequirementsOut`, `KycCompletionOut` TS types in `kyc.ts` (increment 3).
- Produces (used by Tasks 6–7): types `MemberKycRequirementsOut` (same shape as SACCO's), `MemberKycOut { member_id, completion }`, `MemberSelfKycOut { completion }`; `resources.members.getKycRequirements()`, `.putKycRequirements({ required })`, `.getKyc(id)`; `resources.member.getMyKyc()`; `queryKeys.members.kycRequirements()`, `.kyc(id)`, `queryKeys.member.kyc()`.

- [ ] **Step 1: Write the failing test**

Create `admin/packages/api-client/src/__tests__/query-keys-member-kyc.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { queryKeys } from "../query-keys";

describe("member KYC query keys", () => {
  it("members config + per-member completion keys", () => {
    expect(queryKeys.members.kycRequirements()).toEqual(["members", "kycRequirements"]);
    expect(queryKeys.members.kyc("m1")).toEqual(["members", "kyc", "m1"]);
  });

  it("member self completion key", () => {
    expect(queryKeys.member.kyc()).toEqual(["member", "kyc"]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `admin/`): `pnpm --filter @sacco/api-client exec vitest run src/__tests__/query-keys-member-kyc.test.ts`
Expected: FAIL — `kycRequirements` is not a function.

- [ ] **Step 3: Write the implementation**

Append to `admin/packages/schemas/src/kyc.ts`:

```ts
// ---- Member KYC (increment 4). Requirement items share the SACCO shape. ----

export type MemberKycRequirementsOut = SaccoKycRequirementsOut;

export interface MemberKycOut {
  member_id: string;
  completion: KycCompletionOut;
}

export interface MemberSelfKycOut {
  completion: KycCompletionOut;
}
```

In `admin/packages/api-client/src/resources/members.ts`, add to the returned object (before `create:` to keep reads together):

```ts
    getKycRequirements: () => api.GET("/members/kyc-requirements" as never),
    putKycRequirements: (body: { required: Record<string, boolean> }) =>
      api.PUT("/members/kyc-requirements" as never, { body } as never),
    getKyc: (id: string) =>
      api.GET("/members/{member_id}/kyc" as never, {
        params: { path: { member_id: id } },
      } as never),
```

In `admin/packages/api-client/src/resources/member.ts`, add to the returned object:

```ts
    getMyKyc: () => api.GET("/member/me/kyc" as never),
```

In `admin/packages/api-client/src/query-keys.ts`:
- `members` block — add:

```ts
    kycRequirements: () => ["members", "kycRequirements"] as const,
    kyc: (id: string) => ["members", "kyc", id] as const,
```

- `member` block — add:

```ts
    kyc: () => ["member", "kyc"] as const,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pnpm --filter @sacco/api-client exec vitest run src/__tests__/query-keys-member-kyc.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Package checks + commit**

Run: `pnpm --filter @sacco/api-client test && pnpm --filter @sacco/schemas test && pnpm --filter @sacco/api-client typecheck && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/api-client lint && pnpm --filter @sacco/schemas lint`
Expected: all exit 0.

```bash
git add admin/packages/schemas/src/kyc.ts admin/packages/api-client/src/resources/members.ts admin/packages/api-client/src/resources/member.ts admin/packages/api-client/src/query-keys.ts admin/packages/api-client/src/__tests__/query-keys-member-kyc.test.ts
git commit -m "feat(api-client): member KYC types, resources, query keys"
```

---

### Task 6: Shared requirements-toggles component + operator Member KYC requirements page

**Files:**
- Create: `admin/apps/portal/src/components/kyc/KycRequirementsToggles.tsx`
- Modify: `admin/apps/portal/app/platform/(authed)/settings/kyc/_components/SaccoKycRequirementsForm.tsx` (consume the shared component; behavior unchanged)
- Create: `admin/apps/portal/app/(tenant-authed)/organization/member-kyc-requirements/_components/MemberKycRequirementsForm.tsx`
- Create: `admin/apps/portal/app/(tenant-authed)/organization/member-kyc-requirements/page.tsx`
- Modify: `admin/apps/portal/src/components/shell/nav-config.tsx` (second Organization item)
- Test: `admin/apps/portal/app/(tenant-authed)/organization/member-kyc-requirements/__tests__/MemberKycRequirementsForm.test.tsx` (new)

**Interfaces:**
- Consumes: Task 5's `resources.members.getKycRequirements/putKycRequirements`, `queryKeys.members.root()/.kycRequirements()`; `SaccoKycRequirementItemOut` type.
- Produces: `KycRequirementsToggles({ items, description, busy, saveLabel?, onToggle(key, next), onSave() })` — presentational; both wrapper forms own state + mutation.

- [ ] **Step 1: Write the failing test**

Create `admin/apps/portal/app/(tenant-authed)/organization/member-kyc-requirements/__tests__/MemberKycRequirementsForm.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { MemberKycRequirementsOut } from "@sacco/schemas";

const putKycRequirements = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { members: { putKycRequirements } } }),
}));

import { MemberKycRequirementsForm } from "../_components/MemberKycRequirementsForm";

const initial: MemberKycRequirementsOut = {
  items: [
    { key: "full_name", label: "Full name", locked: true, required: true },
    { key: "phone", label: "Phone", locked: false, required: true },
    { key: "occupation", label: "Occupation", locked: false, required: false },
  ],
};

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemberKycRequirementsForm initial={initial} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("MemberKycRequirementsForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("renders locked minimums checked and disabled", () => {
    renderForm();
    const locked = screen.getByRole("checkbox", { name: /full name/i });
    expect(locked).toBeDisabled();
    expect(locked).toBeChecked();
    expect(screen.getByText(/always required/i)).toBeInTheDocument();
  });

  it("saves only the non-locked toggles", async () => {
    putKycRequirements.mockResolvedValue({ data: initial, error: undefined });
    renderForm();

    await userEvent.click(screen.getByRole("checkbox", { name: /phone/i }));
    await userEvent.click(screen.getByRole("checkbox", { name: /occupation/i }));
    await userEvent.click(screen.getByRole("button", { name: /save requirements/i }));

    await waitFor(() => expect(putKycRequirements).toHaveBeenCalledTimes(1));
    expect(putKycRequirements).toHaveBeenCalledWith({
      required: { phone: false, occupation: true },
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pnpm --filter @sacco/portal exec vitest run "app/(tenant-authed)/organization/member-kyc-requirements/__tests__/MemberKycRequirementsForm.test.tsx"`
Expected: FAIL — cannot resolve `../_components/MemberKycRequirementsForm`.

- [ ] **Step 3: Write the implementation**

Create `admin/apps/portal/src/components/kyc/KycRequirementsToggles.tsx` (markup lifted verbatim from the merged `SaccoKycRequirementsForm`; state stays in the wrappers):

```tsx
"use client";

import { Button, Card, Checkbox, Label } from "@sacco/ui";
import type { SaccoKycRequirementItemOut } from "@sacco/schemas";

/**
 * Presentational required-set toggle list shared by the platform SACCO
 * settings page and the operator member settings page. Wrappers own the
 * items state and the save mutation.
 */
export function KycRequirementsToggles({
  items,
  description,
  busy,
  saveLabel = "Save requirements",
  onToggle,
  onSave,
}: {
  items: SaccoKycRequirementItemOut[];
  description: string;
  busy: boolean;
  saveLabel?: string;
  onToggle(key: string, next: boolean): void;
  onSave(): void;
}) {
  return (
    <Card className="flex max-w-xl flex-col gap-4 p-6">
      <p className="text-[13px] text-[var(--text-secondary)]">{description}</p>
      <ul className="flex flex-col">
        {items.map((item) => (
          <li key={item.key} className="flex items-center gap-3 py-2">
            <Checkbox
              id={`req-${item.key}`}
              checked={item.required}
              disabled={item.locked}
              onCheckedChange={(checked) => onToggle(item.key, checked === true)}
            />
            <Label htmlFor={`req-${item.key}`}>{item.label}</Label>
            {item.locked ? (
              <span className="text-[11px] text-[var(--text-tertiary)]">
                Always required
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      <div>
        <Button onClick={onSave} disabled={busy}>
          {saveLabel}
        </Button>
      </div>
    </Card>
  );
}
```

Rewrite `admin/apps/portal/app/platform/(authed)/settings/kyc/_components/SaccoKycRequirementsForm.tsx` to consume it (mutation/toasts/state identical to the merged version — only the JSX moves):

```tsx
"use client";

import { useState } from "react";
import { toast } from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import type { SaccoKycRequirementsOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";
import { KycRequirementsToggles } from "@/components/kyc/KycRequirementsToggles";

export function SaccoKycRequirementsForm({
  initial,
}: {
  initial: SaccoKycRequirementsOut;
}) {
  const { resources } = useAuth();
  const [items, setItems] = useState(initial.items);

  const mutation = useTypedMutation<SaccoKycRequirementsOut, Record<string, boolean>>(
    async (required) => {
      // putSaccoRequirements is typed Promise<never> (as-never paths); cast
      // to the real { data, error } shape.
      const res = await (resources.kyc.putSaccoRequirements({
        required,
      }) as Promise<{ data?: SaccoKycRequirementsOut; error?: unknown }>);
      if (res.error || !res.data) throw res.error ?? new Error("Empty response");
      return res.data;
    },
    {
      invalidates: [queryKeys.kyc.root()],
      onSuccess: (data) => {
        setItems(data.items);
        toast.success("SACCO KYC requirements saved");
      },
      onError: (error) => {
        toast.error("The requirements were not saved", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const toggle = (key: string, next: boolean) => {
    setItems((prev) =>
      prev.map((item) => (item.key === key ? { ...item, required: next } : item)),
    );
  };

  const save = () => {
    mutation.mutate(
      Object.fromEntries(
        items.filter((item) => !item.locked).map((item) => [item.key, item.required]),
      ),
    );
  };

  return (
    <KycRequirementsToggles
      items={items}
      description="Fields required for a SACCO's organization KYC to count as complete. Applies to all tenants. Locked minimums cannot be toggled off."
      busy={mutation.isPending}
      onToggle={toggle}
      onSave={save}
    />
  );
}
```

Create `admin/apps/portal/app/(tenant-authed)/organization/member-kyc-requirements/_components/MemberKycRequirementsForm.tsx`:

```tsx
"use client";

import { useState } from "react";
import { toast } from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import type { MemberKycRequirementsOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";
import { KycRequirementsToggles } from "@/components/kyc/KycRequirementsToggles";

export function MemberKycRequirementsForm({
  initial,
}: {
  initial: MemberKycRequirementsOut;
}) {
  const { resources } = useAuth();
  const [items, setItems] = useState(initial.items);

  const mutation = useTypedMutation<MemberKycRequirementsOut, Record<string, boolean>>(
    async (required) => {
      // putKycRequirements is typed Promise<never> (as-never paths); cast
      // to the real { data, error } shape.
      const res = await (resources.members.putKycRequirements({
        required,
      }) as Promise<{ data?: MemberKycRequirementsOut; error?: unknown }>);
      if (res.error || !res.data) throw res.error ?? new Error("Empty response");
      return res.data;
    },
    {
      invalidates: [queryKeys.members.root(), queryKeys.members.kycRequirements()],
      onSuccess: (data) => {
        setItems(data.items);
        toast.success("Member KYC requirements saved");
      },
      onError: (error) => {
        toast.error("The requirements were not saved", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const toggle = (key: string, next: boolean) => {
    setItems((prev) =>
      prev.map((item) => (item.key === key ? { ...item, required: next } : item)),
    );
  };

  const save = () => {
    mutation.mutate(
      Object.fromEntries(
        items.filter((item) => !item.locked).map((item) => [item.key, item.required]),
      ),
    );
  };

  return (
    <KycRequirementsToggles
      items={items}
      description="Fields a member must provide for their KYC to count as complete in this SACCO. Locked minimums cannot be toggled off. Completion is informational — it does not block activation or transactions."
      busy={mutation.isPending}
      onToggle={toggle}
      onSave={save}
    />
  );
}
```

Create `admin/apps/portal/app/(tenant-authed)/organization/member-kyc-requirements/page.tsx`:

```tsx
import type { MemberKycRequirementsOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { MemberKycRequirementsForm } from "./_components/MemberKycRequirementsForm";

export const metadata = { title: "Member KYC requirements" };

export default async function MemberKycRequirementsPage() {
  const { resources } = await getTenantPageContext();

  // getKycRequirements is typed Promise<never> (as-never paths); cast to
  // the real { data, error } shape.
  const { data, error } = await (resources.members.getKycRequirements() as Promise<{
    data?: MemberKycRequirementsOut;
    error?: unknown;
  }>);
  if (!data) {
    throw new Error(`Failed to load member KYC requirements: ${JSON.stringify(error)}`);
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Member KYC requirements</h1>
      <MemberKycRequirementsForm initial={data} />
    </div>
  );
}
```

Modify `admin/apps/portal/src/components/shell/nav-config.tsx`: add `ListChecks` to the lucide-react import (alphabetical order) and add a second item to the TENANT_NAV "Organization" group:

```ts
  {
    label: "Organization",
    items: [
      { label: "Organization KYC", href: "/organization/kyc", icon: ShieldCheck },
      {
        label: "Member KYC requirements",
        href: "/organization/member-kyc-requirements",
        icon: ListChecks,
      },
    ],
  },
```

- [ ] **Step 4: Run tests to verify they pass — including the existing platform form tests**

Run: `pnpm --filter @sacco/portal exec vitest run "app/(tenant-authed)/organization/member-kyc-requirements/__tests__/MemberKycRequirementsForm.test.tsx" "app/platform/(authed)/settings/kyc/__tests__/SaccoKycRequirementsForm.test.tsx"`
Expected: ALL PASS (2 new + 2 existing — the refactor must not change the platform form's behavior).

- [ ] **Step 5: Checks + commit**

Run: `pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: exit 0.

```bash
git add admin/apps/portal/src/components/kyc/KycRequirementsToggles.tsx "admin/apps/portal/app/platform/(authed)/settings/kyc/_components/SaccoKycRequirementsForm.tsx" "admin/apps/portal/app/(tenant-authed)/organization/member-kyc-requirements/" admin/apps/portal/src/components/shell/nav-config.tsx
git commit -m "feat(portal): operator Member KYC requirements page + shared toggles component"
```

---

### Task 7: Member-detail KYC completion card

**Files:**
- Modify: `admin/apps/portal/app/(tenant-authed)/members/[id]/page.tsx`

**Interfaces:**
- Consumes: Task 5's `resources.members.getKyc(id)` + `MemberKycOut` type; increment 3's `KycCompletionCard` at `@/components/kyc/KycCompletionCard`.
- Produces: the operator member-detail KYC completion card (spec §Portal design → Member detail).

- [ ] **Step 1: Apply the edits**

In `admin/apps/portal/app/(tenant-authed)/members/[id]/page.tsx`:

Add to the imports:

```tsx
import type { MemberKycOut } from "@sacco/schemas";
import { KycCompletionCard } from "@/components/kyc/KycCompletionCard";
```

(merge `MemberKycOut` into the existing `@sacco/schemas` type-import list.)

Extend the existing `Promise.all` with a fifth element:

```tsx
      resources.members.getKyc(id) as Promise<{
        data?: MemberKycOut;
        error?: unknown;
      }>,
```

and the destructuring to match:

```tsx
  const [{ data }, { data: accounts }, { data: shareAccounts }, { data: loans }, { data: kyc }] =
```

Render the card immediately after the existing "KYC" `<Card>` (the one listing ID document fields):

```tsx
      {kyc ? <KycCompletionCard completion={kyc.completion} /> : null}
```

- [ ] **Step 2: Verify**

Run: `pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint && pnpm --filter @sacco/portal test`
Expected: all exit 0 (server pages have no unit harness; the suite guards regressions).

- [ ] **Step 3: Commit**

```bash
git add "admin/apps/portal/app/(tenant-authed)/members/[id]/page.tsx"
git commit -m "feat(portal): KYC completion card on operator member detail"
```

---

### Task 8: Close-out — full suites + CLAUDE.md member-KYC contract

**Files:**
- Modify: `CLAUDE.md` (append one bullet to the existing "## KYC tracking contracts (do not violate)" section)

- [ ] **Step 1: Backend suite**

Run: `python -m ruff check app/ tests/ && python -m mypy app/ && python -m pytest tests/core/ tests/modules/members/ tests/modules/organization/ tests/platform_/kyc/ -q`
Expected: all clean/green.

- [ ] **Step 2: Admin suite**

Run (from `admin/`): `pnpm lint && pnpm typecheck && pnpm test`
Expected: all exit 0.

- [ ] **Step 3: Append the contract bullet**

In `CLAUDE.md`, inside "## KYC tracking contracts (do not violate)", insert before the final "**Gating:**" bullet:

```markdown
- **Member KYC:** the required set is per-tenant (`member_kyc_requirements`,
  operator-owned via `GET/PUT /members/kyc-requirements` — registered BEFORE the
  `/{member_id}` route). Completion is computed by `member_kyc_completion` in
  `app/modules/members/kyc.py` against `MEMBER_KYC_CATALOG` and surfaced on
  `GET /members/{id}/kyc` and `GET /member/me/kyc`. The increment-5 columns
  (`next_of_kin_name`, `next_of_kin_phone`, `occupation`) read as absent until
  they ship. Shared requirement/completion Pydantic schemas live in
  `app/core/kyc/schemas.py`; org/platform modules re-export them.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): member KYC required-set contract (increment 4)"
```

---

## Out of scope for this plan (increment 5)

- `kyc_submissions` table, the three new member columns, member submit/resubmit endpoints, operator review queue + approve/reject screens, member portal Profile → KYC section, `national_id` 409-on-approve.
- Extending `GET /member/me/kyc` with latest-submission status and `MemberSelfKycOut.values`.
- Explicit audit rows for requirement-toggle writes (deferred for both `sacco_kyc_requirements` and `member_kyc_requirements` together).
- The deferred increment-3 minors (whitespace-only-email Zod edge, onError/unverify test gaps) — separate follow-up.
