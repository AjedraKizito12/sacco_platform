# IAM v1-02: Password Hashing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the argon2id password hashing wrapper (`hash_password`, `verify_password`, `needs_rehash`) used by all auth flows that verify user credentials, and add the `AUTH_PASSWORD_MIN_LENGTH` config setting that gates password acceptance at hash time.

**Architecture:** A single `CryptContext` (passlib) configured for argon2id at OWASP-recommended server-side parameters (memory=64 MB, time_cost=3, parallelism=4) is held as a module-level singleton. `hash_password` validates minimum length before hashing. `verify_password` delegates to passlib's constant-time comparison. `needs_rehash` returns `True` when the stored hash uses outdated parameters, allowing transparent rehash on next login. No DB touches; no FastAPI dependencies. This plan can be merged in any order relative to Plan 01.

**Tech Stack:** passlib[argon2] (argon2-cffi backend), pydantic-settings, pytest

---

## Required Reading (complete before starting any task)

1. `CLAUDE.md` — architectural rules; confirm no password logic belongs in `platform_`
2. `docs/superpowers/decisions/2026-05-21-iam-architecture.md` §9 — Password Handling Boundary
3. `docs/superpowers/specs/2026-05-21-iam-v1-design.md` §5 — password hashing spec
4. `app/core/config.py` — existing `Settings` class (add `auth_password_min_length` here)
5. `app/platform_/models.py` — confirm `hashed_password` column is `Text | None`; this plan does not touch that column

---

## File Map

```
CREATE app/modules/iam/passwords/__init__.py
CREATE app/modules/iam/passwords/service.py  — hash_password, verify_password, needs_rehash
CREATE tests/modules/iam/passwords/__init__.py
CREATE tests/modules/iam/passwords/test_password_service.py
MODIFY app/core/config.py                    — add auth_password_min_length setting
```

> **Prerequisite:** `app/modules/iam/__init__.py` must exist (created in Plan 01 Task 2).
> If Plan 01 has not been merged yet, create it with `touch app/modules/iam/__init__.py`.

---

### Task 1: Add `auth_password_min_length` config setting

**Files:**
- Modify: `app/core/config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/core/test_config.py`:

```python
def test_auth_password_min_length_defaults_to_12():
    from app.core.config import Settings

    s = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        app_secret_key="x",
    )
    assert s.auth_password_min_length == 12


def test_auth_password_min_length_is_configurable():
    from app.core.config import Settings

    s = Settings(
        database_url="postgresql+asyncpg://x:x@localhost/x",
        app_secret_key="x",
        auth_password_min_length=16,
    )
    assert s.auth_password_min_length == 16
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/core/test_config.py -v -k "password_min_length"
```

Expected: `ValidationError` or `AttributeError` — field does not exist yet

- [ ] **Step 3: Add the field to `app/core/config.py`**

Add a new `# Password policy` section inside the `Settings` class body, after the JWT block (or after the existing auth settings if Plan 01 is not yet merged):

```python
    # Password policy
    auth_password_min_length: int = 12  # characters; no complexity rules in v1
```

After adding, the relevant section of `Settings` should look like:

```python
    # Platform auth
    platform_auth_mode: str = "stub"  # "stub" | "jwt"
    platform_bootstrap_email: str = ""
    platform_bootstrap_full_name: str = "Platform Admin"

    # Tenant auth
    tenant_auth_mode: str = "stub"  # "stub" | "jwt"

    # JWT signing key infrastructure  ← added by Plan 01; may already exist
    jwt_kek: str = ""
    jwt_key_rotation_days: int = 90
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_platform_seconds: int = 3600
    jwt_refresh_ttl_tenant_seconds: int = 28800

    # Password policy
    auth_password_min_length: int = 12
```

> If Plan 01 has not been merged yet the JWT block will be absent. Add
> `auth_password_min_length` after `platform_bootstrap_full_name` in that case.

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/core/test_config.py -v -k "password_min_length"
```

Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/config.py tests/core/test_config.py
git commit -m "feat(iam): add auth_password_min_length config setting (default 12)"
```

---

### Task 2: Install passlib with argon2 backend

**Files:** none (dependency only)

- [ ] **Step 1: Install the dependency**

```bash
pip install "passlib[argon2]"
```

- [ ] **Step 2: Confirm argon2-cffi is available**

```bash
python -c "
from passlib.context import CryptContext
ctx = CryptContext(schemes=['argon2'], deprecated='auto')
h = ctx.hash('testpassword')
assert ctx.verify('testpassword', h)
print('argon2id OK:', h[:20], '...')
"
```

Expected output: `argon2id OK: $argon2id$v=19$...`

If this prints `$argon2id$` the backend is working. If it raises `ImportError` or falls
back to bcrypt, run `pip install argon2-cffi` explicitly.

- [ ] **Step 3: Add to requirements / pyproject**

Check which dependency file this project uses:

```bash
ls pyproject.toml requirements*.txt 2>/dev/null | head -5
```

Add `passlib[argon2]` (and `argon2-cffi` if listed separately) to the appropriate file.
Do not add version pins beyond what the project already enforces.

---

### Task 3: Password hashing service

**Files:**
- Create: `app/modules/iam/passwords/__init__.py`
- Create: `app/modules/iam/passwords/service.py`
- Create: `tests/modules/iam/passwords/__init__.py`
- Create: `tests/modules/iam/passwords/test_password_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/modules/iam/passwords/test_password_service.py
"""Tests for the argon2id password hashing wrapper.

These tests intentionally use the real argon2id implementation (not mocked)
because the point of the module is correct password hashing. Each hash call
takes ~200–400 ms due to the OWASP-recommended parameters. This is expected
and acceptable — the test suite has ~6 tests here, adding ~2 s total.
"""
import pytest

from app.modules.iam.passwords.service import hash_password, needs_rehash, verify_password


def test_hash_is_not_plaintext():
    hashed = hash_password("CorrectHorseBatteryStaple!")
    assert hashed != "CorrectHorseBatteryStaple!"
    assert "CorrectHorseBatteryStaple" not in hashed


def test_hash_uses_argon2id_scheme():
    hashed = hash_password("CorrectHorseBatteryStaple!")
    # passlib argon2id hashes start with $argon2id$
    assert hashed.startswith("$argon2id$"), f"Unexpected prefix: {hashed[:30]}"


def test_hash_is_non_deterministic():
    # Two hashes of the same password must differ (random salt per call).
    h1 = hash_password("CorrectHorseBatteryStaple!")
    h2 = hash_password("CorrectHorseBatteryStaple!")
    assert h1 != h2


def test_verify_correct_password_returns_true():
    hashed = hash_password("CorrectHorseBatteryStaple!")
    assert verify_password("CorrectHorseBatteryStaple!", hashed) is True


def test_verify_wrong_password_returns_false():
    hashed = hash_password("CorrectHorseBatteryStaple!")
    assert verify_password("WrongPassword123!", hashed) is False


def test_hash_password_rejects_too_short_password():
    # Default minimum is 12 characters; "tooshort" has 8.
    with pytest.raises(ValueError, match="at least 12"):
        hash_password("tooshort")


def test_hash_password_accepts_exactly_minimum_length():
    # 12 characters — exactly at the boundary; must not raise.
    hashed = hash_password("A" * 12)
    assert verify_password("A" * 12, hashed) is True


def test_needs_rehash_returns_false_for_current_parameters():
    hashed = hash_password("CorrectHorseBatteryStaple!")
    # Hash was just produced with the current context — no rehash needed.
    assert needs_rehash(hashed) is False


def test_needs_rehash_returns_true_for_outdated_bcrypt_hash():
    # Simulate a legacy bcrypt hash that was in the DB before argon2id migration.
    # passlib can verify bcrypt, but needs_rehash will return True because
    # the CryptContext only accepts argon2 as non-deprecated.
    from passlib.hash import bcrypt

    legacy_hash = bcrypt.using(rounds=4).hash("CorrectHorseBatteryStaple!")
    # verify still works (passlib handles multiple schemes)
    assert verify_password("CorrectHorseBatteryStaple!", legacy_hash) is True
    # but rehash is needed
    assert needs_rehash(legacy_hash) is True
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/modules/iam/passwords/test_password_service.py -v
```

Expected: `ImportError` — `passwords/service.py` does not exist yet

- [ ] **Step 3: Create `app/modules/iam/passwords/__init__.py`**

```bash
mkdir -p app/modules/iam/passwords tests/modules/iam/passwords
touch app/modules/iam/passwords/__init__.py tests/modules/iam/passwords/__init__.py
```

- [ ] **Step 4: Create `app/modules/iam/passwords/service.py`**

```python
"""argon2id password hashing using passlib.

A single module-level ``CryptContext`` is configured at OWASP-recommended
server-side parameters and reused across all calls. The context lists
``bcrypt`` as a deprecated fallback scheme so that any legacy bcrypt hashes
already in the database can still be verified — ``needs_rehash`` will return
``True`` for those, triggering a transparent upgrade on next successful login.

OWASP argon2id recommendations (server-side, 2023):
    memory_cost  = 64 MB (65536 KiB)
    time_cost    = 3 iterations
    parallelism  = 4 threads

Do not change these defaults without re-reviewing the OWASP guidance and
updating the ``@validator`` in Settings if the minimum-length rule changes.
"""
from __future__ import annotations

from passlib.context import CryptContext

from app.core.config import get_settings

_pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated=["bcrypt"],
    # argon2id parameters — OWASP server-side recommendations.
    argon2__memory_cost=65536,  # 64 MB in KiB
    argon2__time_cost=3,
    argon2__parallelism=4,
)


def hash_password(plain: str) -> str:
    """Hash *plain* using argon2id and return the passlib-formatted hash string.

    Validates minimum password length before hashing. Raises ``ValueError``
    if the password is shorter than ``settings.auth_password_min_length``.

    The returned string is safe to store directly in the ``hashed_password``
    column — it includes the algorithm, version, parameters, salt, and hash
    in a self-describing format (``$argon2id$v=19$...``).
    """
    min_length = get_settings().auth_password_min_length
    if len(plain) < min_length:
        raise ValueError(
            f"Password must be at least {min_length} characters"
        )
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return ``True`` if *plain* matches *hashed*, ``False`` otherwise.

    Uses passlib's constant-time comparison. Safe to call with hashes
    produced by any scheme registered in the context (argon2id or legacy
    bcrypt). Returns ``False`` — never raises — for any verification failure.
    """
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        return False


def needs_rehash(hashed: str) -> bool:
    """Return ``True`` if *hashed* was produced with outdated parameters.

    Call this after a successful ``verify_password`` and, if ``True``,
    immediately hash the plaintext again with ``hash_password`` and persist
    the new hash. This provides transparent parameter upgrades without
    requiring users to change their passwords.

    Returns ``True`` for:
    - Hashes produced with an older argon2id parameter set (e.g., lower
      memory_cost before a future parameter upgrade).
    - Any hash produced by a deprecated scheme (e.g., legacy bcrypt).
    """
    return _pwd_context.needs_update(hashed)
```

- [ ] **Step 5: Run all password tests to confirm pass**

```bash
pytest tests/modules/iam/passwords/test_password_service.py -v
```

Expected: All 9 tests PASS.

> **Note on test speed:** `test_hash_*` tests call the real argon2id hasher. Each
> call takes ~200–400 ms. Total for this file: ~2–3 s. This is intentional — the
> tests must exercise the real implementation, not a mock.

- [ ] **Step 6: Commit**

```bash
git add app/modules/iam/passwords/ tests/modules/iam/passwords/
git commit -m "feat(iam): argon2id password hashing wrapper — hash_password, verify_password, needs_rehash"
```

---

## Verification Criteria

Before marking this plan complete, run the following:

```bash
# 1. Linting
ruff check app/modules/iam/passwords/ app/core/config.py

# 2. Type checking
mypy app/modules/iam/passwords/ app/core/config.py --strict

# 3. Password service tests
pytest tests/modules/iam/passwords/ -v

# 4. Config tests
pytest tests/core/test_config.py -v -k "password_min_length"

# 5. Regression: full suite (password tests will add ~3 s)
pytest tests/ -v
```

All commands must exit cleanly before this plan is considered complete.

---

## What is NOT in this plan

- Calling `hash_password` or `verify_password` from any auth flow — that happens in **Plans 05 and 06** (platform and tenant auth endpoints).
- Transparent rehash on login — wired in **Plans 05 and 06** after `verify_password` returns `True`.
- Password reset flow — **Plan 08**.
- The `hashed_password` column on `platform_users` or `tenant_users` — already exists on `platform_users` (nullable, set by IAM); `tenant_users` column is added in **Plan 04**.
