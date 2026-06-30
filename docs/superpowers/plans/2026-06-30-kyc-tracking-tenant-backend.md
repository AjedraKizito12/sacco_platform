# KYC Fulfilment Tracking — Tenant Track Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared KYC completion tracker (`app/core/kyc/`) and the SACCO (tenant) organization-KYC backend: a self-attested tenant-schema org profile, a platform-global required-set config, and the operator + platform HTTP endpoints — covering increments 1 and 2 of `docs/superpowers/specs/2026-06-30-kyc-fulfilment-tracking-design.md`.

**Architecture:** A pure, dependency-free completion calculator in `app/core/kyc/` computes percent-complete / missing-items / `is_complete` from an entity's values plus an effective required-field set. SACCO org-KYC values live in a tenant-schema `organization_profile` singleton (self-attested by the tenant admin, audited); the required set is platform-global config in `platform.sacco_kyc_requirements`. Operator endpoints (`/organization/kyc`) read/write values within the tenant session; platform endpoints (`/platform/kyc/sacco-requirements`, `/platform/tenants/{id}/kyc[/verify|/unverify]`) manage the global config and the platform-only `verified` flag via the existing `get_session_for_tenant_schema` dependency.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2, pytest + pytest-asyncio, httpx ASGITransport for API tests, ruff + mypy (strict).

## Global Constraints

- All async; no sync DB code. Pydantic schemas in `schemas.py`, SQLAlchemy models in `models.py`, business logic in `service.py`, FastAPI router in `api.py`.
- ruff + mypy (strict, `--strict`) must stay clean. `from __future__ import annotations` at the top of every module.
- Tenant model tables declare **no** schema (resolved at runtime via `search_path`). Platform tables declare `__table_args__ = {"schema": "platform"}`.
- Tenant migrations live in `alembic/tenant/`; platform migrations in `alembic/platform/`. Next revisions: tenant `016` (down_revision `015`), platform `010` (down_revision `009`).
- Every sensitive write goes through `AuditableMixin` (before/after JSON to `audit_log`). Do not write audit rows by hand.
- KYC completion is **informational only** — it must not gate any request path, activation, or transaction.
- `app/core/kyc/` is pure: no DB, no I/O, imports nothing from `app/modules` or `app/platform_`.
- The `verified` flag is set **only** by the platform verify/unverify endpoints, and **only** when completion `is_complete`. Any material org-value change resets `verified=false`.
- Cross-tenant/cross-entity access returns **404**, never 403.
- New `/platform/*` routes gate on `CurrentAdmin` (admin or above). New operator routes gate on `CurrentTenantUser` and are subscription-gated (they use `get_tenant_session`).
- New SQLAlchemy models MUST be imported in `tests/conftest.py`'s `test_engine` fixture (so `Base.metadata.create_all` builds them) and, for tenant models, in `alembic/tenant/env.py` (so autogenerate/metadata is aware).

---

### Task 1: Core KYC catalog

**Files:**
- Create: `app/core/kyc/__init__.py`
- Create: `app/core/kyc/catalog.py`
- Test: `tests/core/kyc/__init__.py`, `tests/core/kyc/test_catalog.py`

**Interfaces:**
- Produces: `FieldSpec(key: str, label: str, locked: bool, default_required: bool)` (frozen dataclass); `SACCO_KYC_CATALOG: tuple[FieldSpec, ...]`; `MEMBER_KYC_CATALOG: tuple[FieldSpec, ...]`.

- [ ] **Step 1: Write the failing test**

Create `tests/core/kyc/__init__.py` (empty) and `tests/core/kyc/test_catalog.py`:

```python
from __future__ import annotations

from app.core.kyc.catalog import (
    MEMBER_KYC_CATALOG,
    SACCO_KYC_CATALOG,
    FieldSpec,
)


def test_sacco_catalog_keys_are_unique() -> None:
    keys = [f.key for f in SACCO_KYC_CATALOG]
    assert len(keys) == len(set(keys))


def test_sacco_locked_minimums() -> None:
    locked = {f.key for f in SACCO_KYC_CATALOG if f.locked}
    assert locked == {
        "legal_name",
        "registration_number",
        "registered_address",
        "primary_contact_name",
        "primary_contact_email",
    }


def test_sacco_toggleable_default_required() -> None:
    toggleable = {f.key for f in SACCO_KYC_CATALOG if not f.locked}
    assert toggleable == {
        "registration_date",
        "regulator_name",
        "license_number",
        "tax_id",
        "primary_contact_phone",
        "postal_address",
        "district_region",
        "country",
    }
    # every toggleable SACCO field defaults to required
    assert all(f.default_required for f in SACCO_KYC_CATALOG if not f.locked)


def test_member_locked_minimums_match_not_null_columns() -> None:
    locked = {f.key for f in MEMBER_KYC_CATALOG if f.locked}
    assert locked == {"full_name", "date_of_birth", "gender"}


def test_fieldspec_is_frozen() -> None:
    spec = FieldSpec(key="x", label="X", locked=False, default_required=True)
    try:
        spec.key = "y"  # type: ignore[misc]
    except Exception as exc:  # noqa: BLE001
        assert "cannot assign" in str(exc).lower() or "frozen" in str(exc).lower()
    else:
        raise AssertionError("FieldSpec must be frozen")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/kyc/test_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.kyc'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/core/kyc/__init__.py`:

```python
from __future__ import annotations
```

Create `app/core/kyc/catalog.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    """One KYC field in a catalog.

    locked: always required; cannot be toggled off (the hard minimums).
    default_required: the required-ness when no config override is present
        (only consulted for non-locked fields).
    """

    key: str
    label: str
    locked: bool
    default_required: bool


SACCO_KYC_CATALOG: tuple[FieldSpec, ...] = (
    FieldSpec("legal_name", "Registered legal name", locked=True, default_required=True),
    FieldSpec("registration_number", "Registration number", locked=True, default_required=True),
    FieldSpec("registered_address", "Registered physical address", locked=True, default_required=True),
    FieldSpec("primary_contact_name", "Primary contact name", locked=True, default_required=True),
    FieldSpec("primary_contact_email", "Primary contact email", locked=True, default_required=True),
    FieldSpec("registration_date", "Date of registration", locked=False, default_required=True),
    FieldSpec("regulator_name", "Regulator", locked=False, default_required=True),
    FieldSpec("license_number", "License number", locked=False, default_required=True),
    FieldSpec("tax_id", "Tax identification number", locked=False, default_required=True),
    FieldSpec("primary_contact_phone", "Primary contact phone", locked=False, default_required=True),
    FieldSpec("postal_address", "Postal address", locked=False, default_required=True),
    FieldSpec("district_region", "District / region", locked=False, default_required=True),
    FieldSpec("country", "Country", locked=False, default_required=True),
)


MEMBER_KYC_CATALOG: tuple[FieldSpec, ...] = (
    FieldSpec("full_name", "Full name", locked=True, default_required=True),
    FieldSpec("date_of_birth", "Date of birth", locked=True, default_required=True),
    FieldSpec("gender", "Gender", locked=True, default_required=True),
    FieldSpec("phone", "Phone", locked=False, default_required=True),
    FieldSpec("email", "Email", locked=False, default_required=True),
    FieldSpec("physical_address", "Physical address", locked=False, default_required=True),
    FieldSpec("national_id_number", "National ID number", locked=False, default_required=True),
    FieldSpec("id_document_type", "ID document type", locked=False, default_required=True),
    FieldSpec("id_document_number", "ID document number", locked=False, default_required=True),
    FieldSpec("id_issued_date", "ID issued date", locked=False, default_required=False),
    FieldSpec("id_expiry_date", "ID expiry date", locked=False, default_required=False),
    FieldSpec("next_of_kin_name", "Next of kin name", locked=False, default_required=True),
    FieldSpec("next_of_kin_phone", "Next of kin phone", locked=False, default_required=True),
    FieldSpec("occupation", "Occupation", locked=False, default_required=False),
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/kyc/test_catalog.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/core/kyc/__init__.py app/core/kyc/catalog.py tests/core/kyc/
git commit -m "feat(core): KYC field catalogs for SACCO and member entities"
```

---

### Task 2: Core completion computation

**Files:**
- Create: `app/core/kyc/completion.py`
- Test: `tests/core/kyc/test_completion.py`

**Interfaces:**
- Consumes: `FieldSpec` from `app/core/kyc/catalog.py`.
- Produces:
  - `FieldStatus(key: str, label: str, required: bool, present: bool)` (frozen dataclass).
  - `KycCompletion(items: tuple[FieldStatus, ...], required_total: int, required_present: int, percent: int, missing_required: tuple[str, ...], is_complete: bool)` (frozen dataclass).
  - `compute_completion(values: Mapping[str, object | None], catalog: Sequence[FieldSpec], required_overrides: Mapping[str, bool]) -> KycCompletion`.

- [ ] **Step 1: Write the failing test**

Create `tests/core/kyc/test_completion.py`:

```python
from __future__ import annotations

from app.core.kyc.catalog import FieldSpec
from app.core.kyc.completion import compute_completion

CATALOG = (
    FieldSpec("a", "A", locked=True, default_required=True),
    FieldSpec("b", "B", locked=False, default_required=True),
    FieldSpec("c", "C", locked=False, default_required=False),
)


def test_locked_field_is_always_required_even_if_override_false() -> None:
    result = compute_completion({"a": None, "b": "x", "c": "y"}, CATALOG, {"a": False})
    a = next(i for i in result.items if i.key == "a")
    assert a.required is True
    assert a.present is False
    assert "a" in result.missing_required
    assert result.is_complete is False


def test_override_makes_default_required_field_optional() -> None:
    # b default-required, overridden off → not counted as missing
    result = compute_completion({"a": "x", "b": None, "c": None}, CATALOG, {"b": False})
    assert result.missing_required == ()
    assert result.is_complete is True
    assert result.percent == 100


def test_blank_string_is_not_present() -> None:
    result = compute_completion({"a": "   ", "b": "x", "c": None}, CATALOG, {})
    a = next(i for i in result.items if i.key == "a")
    assert a.present is False
    assert "a" in result.missing_required


def test_percent_and_counts() -> None:
    # required: a (locked) + b (default) = 2; present required: a only
    result = compute_completion({"a": "x", "b": None, "c": None}, CATALOG, {})
    assert result.required_total == 2
    assert result.required_present == 1
    assert result.percent == 50
    assert result.is_complete is False


def test_no_required_fields_is_100_percent() -> None:
    catalog = (FieldSpec("a", "A", locked=False, default_required=False),)
    result = compute_completion({"a": None}, catalog, {})
    assert result.required_total == 0
    assert result.percent == 100
    assert result.is_complete is True


def test_unknown_override_keys_are_ignored() -> None:
    result = compute_completion({"a": "x", "b": "y", "c": None}, CATALOG, {"zzz": True})
    assert result.is_complete is True


def test_zero_is_present() -> None:
    catalog = (FieldSpec("n", "N", locked=True, default_required=True),)
    result = compute_completion({"n": 0}, catalog, {})
    n = next(i for i in result.items if i.key == "n")
    assert n.present is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/kyc/test_completion.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.kyc.completion'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/core/kyc/completion.py`:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.core.kyc.catalog import FieldSpec


@dataclass(frozen=True)
class FieldStatus:
    key: str
    label: str
    required: bool
    present: bool


@dataclass(frozen=True)
class KycCompletion:
    items: tuple[FieldStatus, ...]
    required_total: int
    required_present: int
    percent: int
    missing_required: tuple[str, ...]
    is_complete: bool


def _is_present(value: object | None) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def _effective_required(spec: FieldSpec, overrides: Mapping[str, bool]) -> bool:
    if spec.locked:
        return True
    return overrides.get(spec.key, spec.default_required)


def compute_completion(
    values: Mapping[str, object | None],
    catalog: Sequence[FieldSpec],
    required_overrides: Mapping[str, bool],
) -> KycCompletion:
    """Compute KYC completion for an entity.

    Pure function. ``required_overrides`` only affects non-locked fields;
    unknown keys are ignored. A field is "present" when its value is not None
    and, for strings, non-blank.
    """
    items: list[FieldStatus] = []
    missing: list[str] = []
    required_total = 0
    required_present = 0

    for spec in catalog:
        required = _effective_required(spec, required_overrides)
        present = _is_present(values.get(spec.key))
        items.append(
            FieldStatus(key=spec.key, label=spec.label, required=required, present=present)
        )
        if required:
            required_total += 1
            if present:
                required_present += 1
            else:
                missing.append(spec.key)

    percent = 100 if required_total == 0 else round(required_present / required_total * 100)

    return KycCompletion(
        items=tuple(items),
        required_total=required_total,
        required_present=required_present,
        percent=percent,
        missing_required=tuple(missing),
        is_complete=not missing,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/kyc/test_completion.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Run mypy + ruff and commit**

Run: `mypy app/core/kyc && ruff check app/core/kyc`
Expected: no errors.

```bash
git add app/core/kyc/completion.py tests/core/kyc/test_completion.py
git commit -m "feat(core): KYC completion computation (percent, missing, is_complete)"
```

---

### Task 3: Platform SACCO requirements model + migration

**Files:**
- Create: `app/platform_/kyc/__init__.py`
- Create: `app/platform_/kyc/models.py`
- Create: `alembic/platform/versions/010_sacco_kyc_requirements.py`
- Modify: `tests/conftest.py` (import the new model in `test_engine`)
- Test: `tests/platform_/kyc/__init__.py`, `tests/platform_/kyc/test_models.py`

**Interfaces:**
- Produces: `SaccoKycRequirement` model with columns `field_key: str` (PK), `is_required: bool`; table `platform.sacco_kyc_requirements`.

- [ ] **Step 1: Write the failing test**

Create `tests/platform_/kyc/__init__.py` (empty) and `tests/platform_/kyc/test_models.py`:

```python
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.platform_.kyc.models import SaccoKycRequirement


async def test_sacco_requirement_roundtrip(test_engine: AsyncEngine) -> None:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.add(SaccoKycRequirement(field_key="tax_id", is_required=False))
        await s.commit()

    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        row = await s.get(SaccoKycRequirement, "tax_id")
        assert row is not None
        assert row.is_required is False

    # cleanup
    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        await s.execute(text("DELETE FROM platform.sacco_kyc_requirements"))
        await s.commit()
```

- [ ] **Step 2: Add the conftest import, then run the test to verify it fails**

In `tests/conftest.py`, inside the `test_engine` fixture's import block (near `import app.platform_.models`), add:

```python
    import app.platform_.kyc.models  # noqa: F401 — registers SaccoKycRequirement in Base.metadata
```

Run: `pytest tests/platform_/kyc/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.platform_.kyc'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/platform_/kyc/__init__.py`:

```python
from __future__ import annotations
```

Create `app/platform_/kyc/models.py`:

```python
from __future__ import annotations

from sqlalchemy import Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SaccoKycRequirement(Base):
    """Platform-global override of a SACCO KYC field's required-ness.

    Override rows only: a missing row means "use the catalog default".
    Locked catalog fields ignore any row here. One row per field_key.
    """

    __tablename__ = "sacco_kyc_requirements"
    __table_args__ = {"schema": "platform"}

    field_key: Mapped[str] = mapped_column(Text, primary_key=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
```

Create `alembic/platform/versions/010_sacco_kyc_requirements.py`:

```python
"""Platform-global SACCO KYC required-set overrides.

Revision: 010
Depends on: 009
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sacco_kyc_requirements",
        sa.Column("field_key", sa.Text(), primary_key=True),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        schema="platform",
    )


def downgrade() -> None:
    op.drop_table("sacco_kyc_requirements", schema="platform")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/platform_/kyc/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/platform_/kyc/__init__.py app/platform_/kyc/models.py \
  alembic/platform/versions/010_sacco_kyc_requirements.py \
  tests/conftest.py tests/platform_/kyc/
git commit -m "feat(platform): sacco_kyc_requirements table for global KYC required-set"
```

---

### Task 4: SaccoKycRequirementsService

**Files:**
- Create: `app/platform_/kyc/service.py`
- Test: `tests/platform_/kyc/test_service.py`

**Interfaces:**
- Consumes: `SaccoKycRequirement` (Task 3); `SACCO_KYC_CATALOG` (Task 1).
- Produces: `SaccoKycRequirementsService(session)` with:
  - `async def effective_required() -> dict[str, bool]` — every catalog key → effective required (locked→True; else override else default).
  - `async def list_config() -> list[tuple[FieldSpec, bool]]` — catalog spec + effective required, in catalog order.
  - `async def replace(overrides: Mapping[str, bool]) -> None` — replace all override rows; locked keys silently ignored; only non-locked keys persisted.

- [ ] **Step 1: Write the failing test**

Create `tests/platform_/kyc/test_service.py`:

```python
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.platform_.kyc.service import SaccoKycRequirementsService


@pytest.fixture
async def psession(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text("SET LOCAL search_path TO platform"))
        yield s
        await s.execute(text("DELETE FROM platform.sacco_kyc_requirements"))
        await s.commit()


async def test_effective_required_defaults_when_no_overrides(psession: AsyncSession) -> None:
    eff = await SaccoKycRequirementsService(psession).effective_required()
    # locked + all toggleable default to required
    assert eff["legal_name"] is True
    assert eff["tax_id"] is True


async def test_override_turns_off_toggleable(psession: AsyncSession) -> None:
    svc = SaccoKycRequirementsService(psession)
    await svc.replace({"tax_id": False, "country": False})
    await psession.commit()
    eff = await svc.effective_required()
    assert eff["tax_id"] is False
    assert eff["country"] is False
    assert eff["regulator_name"] is True  # untouched → default


async def test_replace_ignores_locked_keys(psession: AsyncSession) -> None:
    svc = SaccoKycRequirementsService(psession)
    await svc.replace({"legal_name": False, "tax_id": False})
    await psession.commit()
    eff = await svc.effective_required()
    assert eff["legal_name"] is True  # locked, override ignored
    assert eff["tax_id"] is False


async def test_replace_is_idempotent_replacement(psession: AsyncSession) -> None:
    svc = SaccoKycRequirementsService(psession)
    await svc.replace({"tax_id": False})
    await psession.commit()
    await svc.replace({"country": False})  # tax_id no longer overridden
    await psession.commit()
    eff = await svc.effective_required()
    assert eff["tax_id"] is True
    assert eff["country"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/platform_/kyc/test_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.platform_.kyc.service'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/platform_/kyc/service.py`:

```python
from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kyc.catalog import SACCO_KYC_CATALOG, FieldSpec
from app.platform_.kyc.models import SaccoKycRequirement

_LOCKED = {f.key for f in SACCO_KYC_CATALOG if f.locked}
_TOGGLEABLE = {f.key for f in SACCO_KYC_CATALOG if not f.locked}


class SaccoKycRequirementsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _overrides(self) -> dict[str, bool]:
        rows = (await self._session.execute(select(SaccoKycRequirement))).scalars().all()
        return {r.field_key: r.is_required for r in rows}

    async def effective_required(self) -> dict[str, bool]:
        overrides = await self._overrides()
        result: dict[str, bool] = {}
        for spec in SACCO_KYC_CATALOG:
            if spec.locked:
                result[spec.key] = True
            else:
                result[spec.key] = overrides.get(spec.key, spec.default_required)
        return result

    async def list_config(self) -> list[tuple[FieldSpec, bool]]:
        eff = await self.effective_required()
        return [(spec, eff[spec.key]) for spec in SACCO_KYC_CATALOG]

    async def replace(self, overrides: Mapping[str, bool]) -> None:
        """Replace all override rows. Locked and unknown keys are ignored;
        only non-locked catalog keys are persisted."""
        await self._session.execute(delete(SaccoKycRequirement))
        for key, required in overrides.items():
            if key in _TOGGLEABLE:
                self._session.add(
                    SaccoKycRequirement(field_key=key, is_required=bool(required))
                )
        await self._session.flush()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/platform_/kyc/test_service.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add app/platform_/kyc/service.py tests/platform_/kyc/test_service.py
git commit -m "feat(platform): SaccoKycRequirementsService (effective + replace)"
```

---

### Task 5: Tenant organization_profile model + migration

**Files:**
- Create: `app/modules/organization/__init__.py`
- Create: `app/modules/organization/models.py`
- Create: `alembic/tenant/versions/016_organization_profile.py`
- Modify: `alembic/tenant/env.py` (import the new model)
- Modify: `tests/conftest.py` (import the new model in `test_engine`)
- Test: `tests/modules/organization/__init__.py`, `tests/modules/organization/test_models.py`

**Interfaces:**
- Produces: `OrganizationProfile` model, table `organization_profile` (tenant schema, no `schema=`). Columns: `id` (UUID PK), the 13 SACCO catalog value columns (`legal_name`…`country`; `registration_date` is `Date`, the rest `Text`, all nullable), `verified` (bool default false), `verified_at` (timestamptz nullable), `verified_by_platform_user_id` (UUID nullable), `singleton` (bool default true, unique), `created_at`, `updated_at`. Uses `AuditableMixin`.

- [ ] **Step 1: Write the failing test**

Create `tests/modules/organization/__init__.py` (empty) and `tests/modules/organization/test_models.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.modules.organization.models import OrganizationProfile

SCHEMA = "tenant_test"


def _factory(engine: AsyncEngine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _cleanup(engine: AsyncEngine) -> None:
    async with _factory(engine)() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text("DELETE FROM organization_profile"))
        await s.commit()


async def test_singleton_second_insert_fails(test_engine: AsyncEngine) -> None:
    try:
        async with _factory(test_engine)() as s:
            await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
            s.add(OrganizationProfile(id=uuid.uuid4(), created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
            await s.commit()
        with pytest.raises(IntegrityError):
            async with _factory(test_engine)() as s:
                await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
                s.add(OrganizationProfile(id=uuid.uuid4(), created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
                await s.commit()
    finally:
        await _cleanup(test_engine)


async def test_defaults(test_engine: AsyncEngine) -> None:
    try:
        async with _factory(test_engine)() as s:
            await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
            row = OrganizationProfile(id=uuid.uuid4(), created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
            s.add(row)
            await s.commit()
            await s.refresh(row)
            assert row.verified is False
            assert row.legal_name is None
    finally:
        await _cleanup(test_engine)
```

- [ ] **Step 2: Add the conftest + alembic env imports, then run the test to verify it fails**

In `tests/conftest.py`'s `test_engine` import block, add:

```python
    import app.modules.organization.models  # noqa: F401 — registers OrganizationProfile in Base.metadata
```

In `alembic/tenant/env.py`, after the other tenant model imports (near `import app.modules.savings.models`), add:

```python
import app.modules.organization.models  # noqa: F401 — registers organization_profile in Base.metadata
```

Run: `pytest tests/modules/organization/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.organization'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/modules/organization/__init__.py`:

```python
from __future__ import annotations
```

Create `app/modules/organization/models.py`:

```python
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import TIMESTAMP, Boolean, Date, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.audit.mixin import AuditableMixin
from app.core.db import Base


class OrganizationProfile(AuditableMixin, Base):
    """Singleton SACCO organization KYC profile (one row per tenant schema).

    Self-attested by the tenant admin. ``verified`` is platform-controlled and
    reset to false whenever a catalog value materially changes.
    """

    __tablename__ = "organization_profile"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    legal_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    registered_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_contact_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_contact_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    regulator_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_contact_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    postal_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    district_region: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)

    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", default=False)
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    verified_by_platform_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Singleton guard: constant value + unique constraint → at most one row.
    singleton: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true", default=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("singleton", name="uq_organization_profile_singleton"),
    )
```

Create `alembic/tenant/versions/016_organization_profile.py`:

```python
"""SACCO organization KYC singleton profile.

Revision: 016
Depends on: 015
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organization_profile",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("legal_name", sa.Text(), nullable=True),
        sa.Column("registration_number", sa.Text(), nullable=True),
        sa.Column("registered_address", sa.Text(), nullable=True),
        sa.Column("primary_contact_name", sa.Text(), nullable=True),
        sa.Column("primary_contact_email", sa.Text(), nullable=True),
        sa.Column("registration_date", sa.Date(), nullable=True),
        sa.Column("regulator_name", sa.Text(), nullable=True),
        sa.Column("license_number", sa.Text(), nullable=True),
        sa.Column("tax_id", sa.Text(), nullable=True),
        sa.Column("primary_contact_phone", sa.Text(), nullable=True),
        sa.Column("postal_address", sa.Text(), nullable=True),
        sa.Column("district_region", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("verified_by_platform_user_id", sa.UUID(), nullable=True),
        sa.Column("singleton", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("singleton", name="uq_organization_profile_singleton"),
    )


def downgrade() -> None:
    op.drop_table("organization_profile")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/modules/organization/test_models.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/modules/organization/__init__.py app/modules/organization/models.py \
  alembic/tenant/versions/016_organization_profile.py alembic/tenant/env.py \
  tests/conftest.py tests/modules/organization/
git commit -m "feat(organization): organization_profile singleton model + migration"
```

---

### Task 6: OrganizationKycService

**Files:**
- Create: `app/modules/organization/service.py`
- Test: `tests/modules/organization/test_service.py`

**Interfaces:**
- Consumes: `OrganizationProfile` (Task 5); `SaccoKycRequirementsService` (Task 4); `compute_completion`, `SACCO_KYC_CATALOG` (Tasks 1–2).
- Produces: exception `KycIncomplete(Exception)`; `OrganizationKycService(session)` with:
  - `async def get_or_create() -> OrganizationProfile`
  - `async def get_with_completion() -> tuple[OrganizationProfile, KycCompletion]`
  - `async def upsert(values: Mapping[str, object | None]) -> tuple[OrganizationProfile, KycCompletion]` — writes provided catalog fields; resets `verified` if any catalog value changes.
  - `async def set_verified(*, verified: bool, platform_user_id: uuid.UUID | None) -> OrganizationProfile` — raises `KycIncomplete` if `verified=True` and completion is not complete.
- `_VALUE_KEYS: tuple[str, ...]` — the 13 catalog value column names.

- [ ] **Step 1: Write the failing test**

Create `tests/modules/organization/test_service.py`:

```python
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.modules.organization.service import KycIncomplete, OrganizationKycService

SCHEMA = "tenant_test"

# all 13 catalog fields populated → complete (default requirements)
_FULL = {
    "legal_name": "Umoja SACCO Ltd",
    "registration_number": "RS-12345",
    "registered_address": "1 Kampala Rd",
    "primary_contact_name": "Jane Doe",
    "primary_contact_email": "jane@umoja.test",
    "registration_date": date(2015, 1, 1),
    "regulator_name": "UMRA",
    "license_number": "LIC-99",
    "tax_id": "TIN-555",
    "primary_contact_phone": "+256700000000",
    "postal_address": "PO Box 1",
    "district_region": "Central",
    "country": "Uganda",
}


@pytest.fixture
async def tsession(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))
        yield s
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text("DELETE FROM organization_profile"))
        await s.execute(text("DELETE FROM platform.sacco_kyc_requirements"))
        await s.commit()


async def test_get_or_create_is_idempotent(tsession: AsyncSession) -> None:
    svc = OrganizationKycService(tsession)
    a = await svc.get_or_create()
    await tsession.commit()
    b = await svc.get_or_create()
    assert a.id == b.id


async def test_upsert_incomplete_then_complete(tsession: AsyncSession) -> None:
    svc = OrganizationKycService(tsession)
    _, comp = await svc.upsert({"legal_name": "Umoja SACCO Ltd"})
    await tsession.commit()
    assert comp.is_complete is False
    assert comp.percent < 100

    _, comp2 = await svc.upsert(_FULL)
    await tsession.commit()
    assert comp2.is_complete is True
    assert comp2.percent == 100


async def test_verify_requires_complete(tsession: AsyncSession) -> None:
    svc = OrganizationKycService(tsession)
    await svc.upsert({"legal_name": "x"})
    await tsession.commit()
    with pytest.raises(KycIncomplete):
        await svc.set_verified(verified=True, platform_user_id=uuid.uuid4())


async def test_verify_then_value_change_resets_verified(tsession: AsyncSession) -> None:
    svc = OrganizationKycService(tsession)
    await svc.upsert(_FULL)
    await tsession.commit()
    pid = uuid.uuid4()
    row = await svc.set_verified(verified=True, platform_user_id=pid)
    await tsession.commit()
    assert row.verified is True
    assert row.verified_by_platform_user_id == pid

    row2, _ = await svc.upsert({"legal_name": "Umoja SACCO Limited"})
    await tsession.commit()
    assert row2.verified is False
    assert row2.verified_at is None
    assert row2.verified_by_platform_user_id is None


async def test_upsert_same_values_keeps_verified(tsession: AsyncSession) -> None:
    svc = OrganizationKycService(tsession)
    await svc.upsert(_FULL)
    await tsession.commit()
    await svc.set_verified(verified=True, platform_user_id=uuid.uuid4())
    await tsession.commit()
    # re-submit identical values → no material change → verified stays
    row, _ = await svc.upsert({"legal_name": "Umoja SACCO Ltd"})
    await tsession.commit()
    assert row.verified is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/modules/organization/test_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.organization.service'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/modules/organization/service.py`:

```python
from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kyc.catalog import SACCO_KYC_CATALOG
from app.core.kyc.completion import KycCompletion, compute_completion
from app.modules.organization.models import OrganizationProfile
from app.platform_.kyc.service import SaccoKycRequirementsService

_VALUE_KEYS: tuple[str, ...] = tuple(f.key for f in SACCO_KYC_CATALOG)


class KycIncomplete(Exception):
    """Raised when verifying an organization whose KYC is not complete."""


class OrganizationKycService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self) -> OrganizationProfile:
        row = (
            await self._session.execute(select(OrganizationProfile).limit(1))
        ).scalar_one_or_none()
        if row is None:
            row = OrganizationProfile()
            self._session.add(row)
            await self._session.flush()
        return row

    def _values(self, row: OrganizationProfile) -> dict[str, object | None]:
        return {key: getattr(row, key) for key in _VALUE_KEYS}

    async def _completion(self, row: OrganizationProfile) -> KycCompletion:
        overrides = await SaccoKycRequirementsService(self._session).effective_required()
        # effective_required already resolves locked/default; pass as overrides
        # (locked keys map to True, which compute_completion re-applies safely).
        return compute_completion(self._values(row), SACCO_KYC_CATALOG, overrides)

    async def get_with_completion(self) -> tuple[OrganizationProfile, KycCompletion]:
        row = await self.get_or_create()
        return row, await self._completion(row)

    async def upsert(
        self, values: Mapping[str, object | None]
    ) -> tuple[OrganizationProfile, KycCompletion]:
        row = await self.get_or_create()
        changed = False
        for key in _VALUE_KEYS:
            if key in values and getattr(row, key) != values[key]:
                setattr(row, key, values[key])
                changed = True
        if changed and row.verified:
            row.verified = False
            row.verified_at = None
            row.verified_by_platform_user_id = None
        await self._session.flush()
        return row, await self._completion(row)

    async def set_verified(
        self, *, verified: bool, platform_user_id: uuid.UUID | None
    ) -> OrganizationProfile:
        row = await self.get_or_create()
        if verified:
            completion = await self._completion(row)
            if not completion.is_complete:
                raise KycIncomplete(
                    f"{len(completion.missing_required)} required field(s) missing"
                )
            row.verified = True
            row.verified_at = datetime.now(UTC)
            row.verified_by_platform_user_id = platform_user_id
        else:
            row.verified = False
            row.verified_at = None
            row.verified_by_platform_user_id = None
        await self._session.flush()
        return row
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/modules/organization/test_service.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Run mypy and commit**

Run: `mypy app/modules/organization app/platform_/kyc app/core/kyc`
Expected: no errors.

```bash
git add app/modules/organization/service.py tests/modules/organization/test_service.py
git commit -m "feat(organization): OrganizationKycService (upsert, verify, completion)"
```

---

### Task 7: Pydantic schemas

**Files:**
- Create: `app/modules/organization/schemas.py`
- Create: `app/platform_/kyc/schemas.py`
- Test: `tests/modules/organization/test_schemas.py`

**Interfaces:**
- Produces (organization): `KycFieldStatusOut`, `KycCompletionOut`, `OrganizationKycValuesIn`, `OrganizationKycOut` with a classmethod `from_row_and_completion(row, completion) -> OrganizationKycOut`.
- Produces (platform kyc): `SaccoKycRequirementItemOut`, `SaccoKycRequirementsOut`, `SaccoKycRequirementsIn` (`required: dict[str, bool]`).

- [ ] **Step 1: Write the failing test**

Create `tests/modules/organization/test_schemas.py`:

```python
from __future__ import annotations

from app.core.kyc.catalog import SACCO_KYC_CATALOG
from app.core.kyc.completion import compute_completion
from app.modules.organization.models import OrganizationProfile
from app.modules.organization.schemas import OrganizationKycOut


def test_organization_kyc_out_maps_values_and_completion() -> None:
    row = OrganizationProfile(legal_name="Umoja", tax_id="T-1")
    completion = compute_completion(
        {f.key: getattr(row, f.key, None) for f in SACCO_KYC_CATALOG},
        SACCO_KYC_CATALOG,
        {},
    )
    out = OrganizationKycOut.from_row_and_completion(row, completion)
    assert out.values.legal_name == "Umoja"
    assert out.values.tax_id == "T-1"
    assert out.verified is False
    assert out.completion.is_complete is False
    assert any(i.key == "legal_name" and i.present for i in out.completion.items)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/modules/organization/test_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.organization.schemas'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/modules/organization/schemas.py`:

```python
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.core.kyc.completion import KycCompletion
from app.modules.organization.models import OrganizationProfile


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
    def from_completion(cls, c: KycCompletion) -> "KycCompletionOut":
        return cls(
            items=[
                KycFieldStatusOut(key=i.key, label=i.label, required=i.required, present=i.present)
                for i in c.items
            ],
            required_total=c.required_total,
            required_present=c.required_present,
            percent=c.percent,
            missing_required=list(c.missing_required),
            is_complete=c.is_complete,
        )


class OrganizationKycValuesIn(BaseModel):
    legal_name: str | None = None
    registration_number: str | None = None
    registered_address: str | None = None
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    registration_date: date | None = None
    regulator_name: str | None = None
    license_number: str | None = None
    tax_id: str | None = None
    primary_contact_phone: str | None = None
    postal_address: str | None = None
    district_region: str | None = None
    country: str | None = None


class OrganizationKycValuesOut(OrganizationKycValuesIn):
    model_config = {"from_attributes": True}


class OrganizationKycOut(BaseModel):
    values: OrganizationKycValuesOut
    verified: bool
    verified_at: datetime | None
    verified_by_platform_user_id: uuid.UUID | None
    completion: KycCompletionOut

    @classmethod
    def from_row_and_completion(
        cls, row: OrganizationProfile, completion: KycCompletion
    ) -> "OrganizationKycOut":
        return cls(
            values=OrganizationKycValuesOut.model_validate(row),
            verified=row.verified,
            verified_at=row.verified_at,
            verified_by_platform_user_id=row.verified_by_platform_user_id,
            completion=KycCompletionOut.from_completion(completion),
        )
```

Create `app/platform_/kyc/schemas.py`:

```python
from __future__ import annotations

from pydantic import BaseModel

from app.core.kyc.catalog import FieldSpec


class SaccoKycRequirementItemOut(BaseModel):
    key: str
    label: str
    locked: bool
    required: bool


class SaccoKycRequirementsOut(BaseModel):
    items: list[SaccoKycRequirementItemOut]

    @classmethod
    def from_config(cls, config: list[tuple[FieldSpec, bool]]) -> "SaccoKycRequirementsOut":
        return cls(
            items=[
                SaccoKycRequirementItemOut(
                    key=spec.key, label=spec.label, locked=spec.locked, required=required
                )
                for spec, required in config
            ]
        )


class SaccoKycRequirementsIn(BaseModel):
    """Map of field_key → required. Locked/unknown keys are ignored server-side."""

    required: dict[str, bool]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/modules/organization/test_schemas.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/modules/organization/schemas.py app/platform_/kyc/schemas.py \
  tests/modules/organization/test_schemas.py
git commit -m "feat(kyc): Pydantic schemas for org KYC values, completion, sacco requirements"
```

---

### Task 8: Operator `/organization/kyc` router + mount

**Files:**
- Create: `app/modules/organization/api.py`
- Modify: `app/main.py` (import + `include_router`)
- Test: `tests/modules/organization/test_api.py`

**Interfaces:**
- Consumes: `OrganizationKycService` (Task 6); `OrganizationKycOut`, `OrganizationKycValuesIn` (Task 7); `CurrentTenantUser` from `app.modules.iam.dependencies`; `get_tenant_session` from `app.core.db`.
- Produces: `router` (prefix `/organization`, tag `organization`) with `GET /organization/kyc` and `PUT /organization/kyc`, both returning `OrganizationKycOut`.

- [ ] **Step 1: Write the failing test**

Create `tests/modules/organization/test_api.py`. This copies the **stub-auth** client fixture from `tests/modules/members/test_api.py` verbatim: override only `get_tenant_session`, reuse the conftest `tenant_actor_id` fixture (it seeds a `TenantUser` in `tenant_test`), and authenticate by setting the `X-Tenant-Actor-ID` / `X-Tenant-Slug` headers (stub tenant auth resolves the seeded user). Do **not** override the auth dependency.

```python
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_tenant_session
from app.main import app, lifespan

SCHEMA = "tenant_test"


async def _tenant_session_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as session:
            await session.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


@pytest.fixture
async def client(
    test_engine: AsyncEngine, tenant_actor_id: uuid.UUID
) -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_tenant_session] = await _tenant_session_override(test_engine)
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
        await s.execute(text("DELETE FROM organization_profile"))
        await s.commit()


async def test_get_creates_empty_profile(client: AsyncClient) -> None:
    resp = await client.get("/organization/kyc")
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is False
    assert body["completion"]["is_complete"] is False
    assert body["values"]["legal_name"] is None


async def test_put_updates_values_and_completion(client: AsyncClient) -> None:
    resp = await client.put("/organization/kyc", json={"legal_name": "Umoja SACCO"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["values"]["legal_name"] == "Umoja SACCO"
    assert any(
        i["key"] == "legal_name" and i["present"] for i in body["completion"]["items"]
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/modules/organization/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.organization.api'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/modules/organization/api.py`:

```python
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_tenant_session
from app.modules.iam.dependencies import CurrentTenantUser
from app.modules.organization.schemas import OrganizationKycOut, OrganizationKycValuesIn
from app.modules.organization.service import OrganizationKycService

router = APIRouter(prefix="/organization", tags=["organization"])

Session = Annotated[AsyncSession, Depends(get_tenant_session)]


@router.get("/kyc", response_model=OrganizationKycOut)
async def get_organization_kyc(
    session: Session, _user: CurrentTenantUser
) -> OrganizationKycOut:
    row, completion = await OrganizationKycService(session).get_with_completion()
    return OrganizationKycOut.from_row_and_completion(row, completion)


@router.put("/kyc", response_model=OrganizationKycOut)
async def put_organization_kyc(
    body: OrganizationKycValuesIn, session: Session, _user: CurrentTenantUser
) -> OrganizationKycOut:
    row, completion = await OrganizationKycService(session).upsert(
        body.model_dump(exclude_unset=True)
    )
    return OrganizationKycOut.from_row_and_completion(row, completion)
```

In `app/main.py`, add the import alongside the other module routers (near line 33):

```python
from app.modules.organization.api import router as organization_router
```

and register it alongside the other `app.include_router(...)` calls (near line 149):

```python
app.include_router(organization_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/modules/organization/test_api.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/modules/organization/api.py app/main.py tests/modules/organization/test_api.py
git commit -m "feat(organization): operator /organization/kyc GET+PUT endpoints"
```

---

### Task 9: Platform KYC router (requirements + tenant oversight + verify) + mount

**Files:**
- Create: `app/platform_/kyc/api.py`
- Modify: `app/main.py` (import + `include_router`)
- Test: `tests/platform_/kyc/test_api.py`

**Interfaces:**
- Consumes: `SaccoKycRequirementsService` (Task 4); `OrganizationKycService`, `KycIncomplete` (Task 6); `SaccoKycRequirementsOut/In` (Task 7); `OrganizationKycOut` (Task 7); `CurrentAdmin` from `app.platform_.auth`; `get_platform_session`, `get_session_for_tenant_schema` from `app.core.db`.
- Produces: `router` with:
  - `GET /platform/kyc/sacco-requirements` → `SaccoKycRequirementsOut` (platform session).
  - `PUT /platform/kyc/sacco-requirements` → `SaccoKycRequirementsOut` (platform session).
  - `GET /platform/tenants/{tenant_id}/kyc` → `OrganizationKycOut` (tenant-schema session).
  - `POST /platform/tenants/{tenant_id}/kyc/verify` → `OrganizationKycOut`; **409** when not complete.
  - `POST /platform/tenants/{tenant_id}/kyc/unverify` → `OrganizationKycOut`.

- [ ] **Step 1: Write the failing test**

Create `tests/platform_/kyc/test_api.py`. Use **platform stub auth** (seed an admin `PlatformUser`, pass the `X-Platform-Actor-ID` header) like `tests/platform_/tenant_users_admin/test_api.py` — do **not** override the role-factory dependency (`get_current_platform_user_with_role("admin")` returns a fresh closure each call, so an override won't match the one captured in `CurrentAdmin`). Override only the two session deps; stub auth resolves the seeded admin and the `admin` role passes the `with_role("admin")` check.

```python
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import get_platform_session, get_session_for_tenant_schema
from app.main import app, lifespan
from app.modules.organization.models import OrganizationProfile
from app.platform_.models import PlatformUser

SCHEMA = "tenant_test"
TENANT_ID = uuid.uuid4()


def _platform_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as s:
            await s.execute(text("SET LOCAL search_path TO platform"))
            s.sync_session.info["is_platform"] = True
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    return _override


def _tenant_schema_override(engine: AsyncEngine):  # type: ignore[no-untyped-def]
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _override(tenant_id: uuid.UUID) -> AsyncGenerator[AsyncSession, None]:
        async with factory() as s:
            await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    return _override


async def _seed_admin(engine: AsyncEngine) -> uuid.UUID:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    admin_id = uuid.uuid4()
    async with factory() as s, s.begin():
        await s.execute(text("SET LOCAL search_path TO platform"))
        s.add(
            PlatformUser(
                id=admin_id,
                email=f"admin-{admin_id.hex[:6]}@p.test",
                full_name="Admin",
                is_active=True,
                is_superuser=False,
                role="admin",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
    return admin_id


async def _seed_full_profile(engine: AsyncEngine) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s, s.begin():
        await s.execute(text(f"SET LOCAL search_path TO {SCHEMA}, platform"))
        s.add(
            OrganizationProfile(
                id=uuid.uuid4(),
                legal_name="Umoja SACCO Ltd",
                registration_number="RS-1",
                registered_address="1 Rd",
                primary_contact_name="Jane",
                primary_contact_email="jane@umoja.test",
                registration_date=date(2015, 1, 1),
                regulator_name="UMRA",
                license_number="LIC-9",
                tax_id="TIN-5",
                primary_contact_phone="+256700000000",
                postal_address="PO 1",
                district_region="Central",
                country="Uganda",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )


@pytest.fixture
async def client(test_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    admin_id = await _seed_admin(test_engine)
    app.dependency_overrides[get_platform_session] = _platform_override(test_engine)
    app.dependency_overrides[get_session_for_tenant_schema] = _tenant_schema_override(test_engine)
    async with lifespan(app), AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        c.headers["X-Platform-Actor-ID"] = str(admin_id)
        yield c
    app.dependency_overrides.pop(get_platform_session, None)
    app.dependency_overrides.pop(get_session_for_tenant_schema, None)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text(f"SET search_path TO {SCHEMA}, platform"))
        await s.execute(text("DELETE FROM organization_profile"))
        await s.execute(text("DELETE FROM platform.sacco_kyc_requirements"))
        await s.execute(
            text("DELETE FROM platform.platform_users WHERE id = :id"), {"id": admin_id}
        )
        await s.commit()


async def test_get_sacco_requirements(client: AsyncClient) -> None:
    resp = await client.get("/platform/kyc/sacco-requirements")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert "legal_name" in {i["key"] for i in items if i["locked"]}


async def test_put_sacco_requirements_toggles_off(client: AsyncClient) -> None:
    resp = await client.put(
        "/platform/kyc/sacco-requirements", json={"required": {"tax_id": False}}
    )
    assert resp.status_code == 200
    tax = next(i for i in resp.json()["items"] if i["key"] == "tax_id")
    assert tax["required"] is False


async def test_verify_incomplete_returns_409(client: AsyncClient) -> None:
    resp = await client.post(f"/platform/tenants/{TENANT_ID}/kyc/verify")
    assert resp.status_code == 409


async def test_verify_after_complete(client: AsyncClient, test_engine: AsyncEngine) -> None:
    await _seed_full_profile(test_engine)
    resp = await client.post(f"/platform/tenants/{TENANT_ID}/kyc/verify")
    assert resp.status_code == 200
    assert resp.json()["verified"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/platform_/kyc/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.platform_.kyc.api'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/platform_/kyc/api.py`:

```python
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_platform_session, get_session_for_tenant_schema
from app.modules.organization.schemas import OrganizationKycOut
from app.modules.organization.service import KycIncomplete, OrganizationKycService
from app.platform_.auth import CurrentAdmin
from app.platform_.kyc.schemas import SaccoKycRequirementsIn, SaccoKycRequirementsOut
from app.platform_.kyc.service import SaccoKycRequirementsService

router = APIRouter(prefix="/platform", tags=["platform-kyc"])

PlatformSession = Annotated[AsyncSession, Depends(get_platform_session)]
TenantSchemaSession = Annotated[AsyncSession, Depends(get_session_for_tenant_schema)]


@router.get("/kyc/sacco-requirements", response_model=SaccoKycRequirementsOut)
async def get_sacco_requirements(
    session: PlatformSession, _user: CurrentAdmin
) -> SaccoKycRequirementsOut:
    config = await SaccoKycRequirementsService(session).list_config()
    return SaccoKycRequirementsOut.from_config(config)


@router.put("/kyc/sacco-requirements", response_model=SaccoKycRequirementsOut)
async def put_sacco_requirements(
    body: SaccoKycRequirementsIn, session: PlatformSession, _user: CurrentAdmin
) -> SaccoKycRequirementsOut:
    svc = SaccoKycRequirementsService(session)
    await svc.replace(body.required)
    config = await svc.list_config()
    return SaccoKycRequirementsOut.from_config(config)


@router.get("/tenants/{tenant_id}/kyc", response_model=OrganizationKycOut)
async def get_tenant_kyc(
    tenant_id: uuid.UUID,  # noqa: ARG001 — consumed by the dep
    session: TenantSchemaSession,
    _user: CurrentAdmin,
) -> OrganizationKycOut:
    row, completion = await OrganizationKycService(session).get_with_completion()
    return OrganizationKycOut.from_row_and_completion(row, completion)


@router.post("/tenants/{tenant_id}/kyc/verify", response_model=OrganizationKycOut)
async def verify_tenant_kyc(
    tenant_id: uuid.UUID,  # noqa: ARG001 — consumed by the dep
    session: TenantSchemaSession,
    user: CurrentAdmin,
) -> OrganizationKycOut:
    svc = OrganizationKycService(session)
    try:
        await svc.set_verified(verified=True, platform_user_id=user.id)
    except KycIncomplete as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    row, completion = await svc.get_with_completion()
    return OrganizationKycOut.from_row_and_completion(row, completion)


@router.post("/tenants/{tenant_id}/kyc/unverify", response_model=OrganizationKycOut)
async def unverify_tenant_kyc(
    tenant_id: uuid.UUID,  # noqa: ARG001 — consumed by the dep
    session: TenantSchemaSession,
    _user: CurrentAdmin,
) -> OrganizationKycOut:
    svc = OrganizationKycService(session)
    await svc.set_verified(verified=False, platform_user_id=None)
    row, completion = await svc.get_with_completion()
    return OrganizationKycOut.from_row_and_completion(row, completion)
```

In `app/main.py`, add the import alongside the other platform routers (near line 58):

```python
from app.platform_.kyc.api import router as platform_kyc_router
```

and register it with the other platform `include_router` calls:

```python
app.include_router(platform_kyc_router)
```

> Audit note: the verify/unverify writes happen inside a tenant-schema session and go through `AuditableMixin`, producing a tenant `audit_log` row. The actor context (`actor_type='platform_user'`, `actor_id`) is bound by the platform auth dependency's structlog contextvars — no extra wiring needed here. Confirm a row is written by checking `tenant_test.audit_log` after the verify test if you want belt-and-suspenders coverage.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/platform_/kyc/test_api.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full new-code suite + lint, then commit**

Run:
```bash
pytest tests/core/kyc tests/modules/organization tests/platform_/kyc -v
mypy app/core/kyc app/modules/organization app/platform_/kyc
ruff check app/core/kyc app/modules/organization app/platform_/kyc
```
Expected: all green.

```bash
git add app/platform_/kyc/api.py app/main.py tests/platform_/kyc/test_api.py
git commit -m "feat(platform): /platform/kyc requirements + tenant KYC oversight/verify endpoints"
```

---

## Self-Review

**Spec coverage (this plan = increments 1 & 2 of the design):**
- Shared tracker (`app/core/kyc/`, pure) → Tasks 1–2. ✓
- SACCO catalog + locked minimums → Task 1. ✓
- `organization_profile` singleton (tenant schema, AuditableMixin, verified fields) → Task 5. ✓
- Platform-global `sacco_kyc_requirements` + service → Tasks 3–4. ✓
- `OrganizationKycService` (get-or-create, upsert with verified-reset, set_verified with incomplete-guard) → Task 6. ✓
- Operator `/organization/kyc` GET/PUT → Task 8. ✓
- Platform `/platform/kyc/sacco-requirements` GET/PUT + `/platform/tenants/{id}/kyc` GET + verify/unverify (409 when incomplete) → Task 9. ✓
- Cross-schema reads via `get_session_for_tenant_schema` and tenant-session reading `platform.sacco_kyc_requirements` → Tasks 6, 9. ✓
- Audit via AuditableMixin; informational-only (no gating) → Tasks 5–9 (no gate added anywhere). ✓
- Member side (increments 4–5) and all portals (increment 3) → **out of scope for this plan** (separate plans), per the design's build sequence.

**Placeholder scan:** none. Every step contains complete code, including both API-test files (Tasks 8 & 9), which now use the project's real stub-auth pattern with self-contained seed helpers.

**Type consistency:** `compute_completion(values, catalog, required_overrides)` signature is consistent across Tasks 2, 6. `effective_required() -> dict[str, bool]` is consumed by `OrganizationKycService._completion` as the `required_overrides` arg (locked keys resolve to `True`, which `compute_completion` re-applies idempotently — verified by Task 2's locked-field test). `OrganizationKycOut.from_row_and_completion` and `KycCompletionOut.from_completion` names match across Tasks 7–9. `_VALUE_KEYS` is defined once (Task 6) from the catalog.

**Auth-test pattern (verified against the codebase):** both API tests authenticate via **stub auth**, not dependency overrides of the auth callables. Tenant operator routes (Task 8): override `get_tenant_session`, reuse the conftest `tenant_actor_id` fixture, send `X-Tenant-Actor-ID` + `X-Tenant-Slug` headers (matches `tests/modules/members/test_api.py`). Platform routes (Task 9): seed an admin `PlatformUser`, override `get_platform_session` + `get_session_for_tenant_schema`, send `X-Platform-Actor-ID` (matches `tests/platform_/tenant_users_admin/test_api.py`). Do **not** override `get_current_platform_user_with_role("admin")` — it returns a fresh closure per call and would not match the instance captured in `CurrentAdmin`. This assumes the test environment runs `PLATFORM_AUTH_MODE=stub` / `TENANT_AUTH_MODE=stub` (the repo default for tests).
