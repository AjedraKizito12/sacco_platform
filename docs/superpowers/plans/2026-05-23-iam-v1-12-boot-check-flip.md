# IAM v1-12: Boot-Check Flip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flip `PLATFORM_AUTH_MODE` and `TENANT_AUTH_MODE` defaults from `"stub"` to `"jwt"`, enforce `JWT_KEK` presence at settings-load time when jwt mode is active, complete `.env.example` with all IAM variables, and document IAM invariants in `CLAUDE.md`.

**Architecture:** Three non-code changes and one config change. The config change (flipping defaults + adding a model validator) is the only change that can break things — it is safe because `tests/conftest.py` already calls `os.environ.setdefault("PLATFORM_AUTH_MODE", "stub")` and `os.environ.setdefault("TENANT_AUTH_MODE", "stub")` before the `Settings` lru_cache is populated. One existing config test (`test_jwt_kek_validator_accepts_empty_string`) must be updated to pass stub auth modes alongside the empty KEK, because the new model validator will now reject jwt+empty-kek at construction time rather than deferring to the lifespan.

**Tech Stack:** pydantic-settings `model_validator`, pytest, shell scripting for keygen example

---

## Required Reading (complete before starting any task)

1. `CLAUDE.md` — current contracts sections; this plan adds a new one
2. `app/core/config.py` — current Settings class; note the `field_validator("jwt_kek")` added by Plan 01
3. `tests/conftest.py` — confirm `os.environ.setdefault` calls for `PLATFORM_AUTH_MODE`, `TENANT_AUTH_MODE`, and `JWT_KEK` are all present (Plans 01 and 09 add these)
4. `tests/core/test_config.py` — find `test_jwt_kek_validator_accepts_empty_string`; this test must be updated in Task 1
5. `.env.example` — current contents; Task 2 overwrites it completely
6. `docs/superpowers/plans/2026-05-23-iam-v1-01-jwt-infrastructure.md` — JWT settings defaults (TTL values, rotation days)
7. `docs/superpowers/plans/2026-05-23-iam-v1-09-dependency-swap.md` Task 4 — the lifespan boot guard already added for `TENANT_AUTH_MODE`; do NOT re-add it here

---

## Prerequisite Check

Before starting Task 1, verify all prior plans are merged:

```bash
# All 11 plan stubs must be replaced
grep -rn "Plan 1[0-2] adds\|Plan [0-9] adds" app/modules/iam/
# Expected: no output (or only "Plan 12 adds" comments if any were left in earlier plans)

# conftest must have all three setdefault calls
grep "setdefault" tests/conftest.py
# Expected: lines for PLATFORM_AUTH_MODE, TENANT_AUTH_MODE, and JWT_KEK
```

---

## File Map

```
MODIFY app/core/config.py                  — flip defaults; add model_validator for jwt_kek requirement
MODIFY tests/core/test_config.py           — update test_jwt_kek_validator_accepts_empty_string
OVERWRITE .env.example                     — complete with all IAM variables
MODIFY CLAUDE.md                           — add IAM module contracts section; update platform_ contracts note
```

---

### Task 1: Flip defaults and enforce JWT_KEK at settings-load time

**Files:**
- Modify: `app/core/config.py`
- Modify: `tests/core/test_config.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to `tests/core/test_config.py` (or create the file if absent):

```python
import base64
import pytest
from pydantic import ValidationError
from app.core.config import Settings


_VALID_KEK = base64.b64encode(b"\x01" * 32).decode()
_STUB_OVERRIDES = {"platform_auth_mode": "stub", "tenant_auth_mode": "stub"}


def test_platform_auth_mode_default_is_jwt():
    """After Plan 12 the default for PLATFORM_AUTH_MODE is 'jwt'."""
    s = Settings(database_url="postgresql://x", app_secret_key="y", jwt_kek=_VALID_KEK)
    assert s.platform_auth_mode == "jwt"


def test_tenant_auth_mode_default_is_jwt():
    """After Plan 12 the default for TENANT_AUTH_MODE is 'jwt'."""
    s = Settings(database_url="postgresql://x", app_secret_key="y", jwt_kek=_VALID_KEK)
    assert s.tenant_auth_mode == "jwt"


def test_model_validator_rejects_empty_kek_with_jwt_platform_mode():
    with pytest.raises(ValidationError, match="JWT_KEK"):
        Settings(
            database_url="postgresql://x",
            app_secret_key="y",
            platform_auth_mode="jwt",
            tenant_auth_mode="stub",
            jwt_kek="",
        )


def test_model_validator_rejects_empty_kek_with_jwt_tenant_mode():
    with pytest.raises(ValidationError, match="JWT_KEK"):
        Settings(
            database_url="postgresql://x",
            app_secret_key="y",
            platform_auth_mode="stub",
            tenant_auth_mode="jwt",
            jwt_kek="",
        )


def test_model_validator_permits_empty_kek_in_full_stub_mode():
    """Both modes stub → jwt_kek not required."""
    s = Settings(
        database_url="postgresql://x",
        app_secret_key="y",
        platform_auth_mode="stub",
        tenant_auth_mode="stub",
        jwt_kek="",
    )
    assert s.jwt_kek == ""


def test_model_validator_accepts_valid_kek_with_jwt_modes():
    s = Settings(
        database_url="postgresql://x",
        app_secret_key="y",
        platform_auth_mode="jwt",
        tenant_auth_mode="jwt",
        jwt_kek=_VALID_KEK,
    )
    assert s.jwt_kek == _VALID_KEK
```

Also find the existing `test_jwt_kek_validator_accepts_empty_string` test and update it so that it explicitly sets stub auth modes (to avoid the new model validator):

```python
def test_jwt_kek_validator_accepts_empty_string():
    """Field-level validator accepts empty string — model validator permits it
    when auth modes are stub. Production enforcement is handled by the model
    validator (test_model_validator_rejects_empty_kek_with_jwt_* tests above)."""
    s = Settings(
        database_url="postgresql://x",
        app_secret_key="y",
        platform_auth_mode="stub",   # <-- added
        tenant_auth_mode="stub",     # <-- added
        jwt_kek="",
    )
    assert s.jwt_kek == ""
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/core/test_config.py -v -k "default_is_jwt or model_validator"
```

Expected: the `default_is_jwt` tests FAIL (defaults are still "stub"), the `model_validator` tests FAIL (validator doesn't exist yet). The updated `test_jwt_kek_validator_accepts_empty_string` test PASSES (it now passes stub modes explicitly, so no regression).

- [ ] **Step 3: Update `app/core/config.py`**

Make three changes:

**3a — Add `model_validator` to imports** (at top of file):

```python
from functools import lru_cache

import base64

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
```

**3b — Flip defaults** in the `Settings` class body. Change:

```python
    platform_auth_mode: str = "stub"  # change to 'jwt' when IAM ships
```

to:

```python
    platform_auth_mode: str = "jwt"  # "stub" | "jwt" — stub requires explicit opt-in
```

And change (Plan 01/09 added this field):

```python
    tenant_auth_mode: str = "stub"  # "stub" | "jwt"
```

to:

```python
    tenant_auth_mode: str = "jwt"  # "stub" | "jwt" — stub requires explicit opt-in
```

**3c — Add `model_validator`** after the existing `field_validator("jwt_kek")` method, still inside the `Settings` class:

```python
    @model_validator(mode="after")
    def validate_kek_required_for_jwt_mode(self) -> "Settings":
        """Require a non-empty JWT_KEK whenever either auth mode is 'jwt'.

        The field-level validator (validate_jwt_kek) already enforces that if
        jwt_kek is non-empty it must be valid base64 of exactly 32 bytes. This
        model-level validator enforces that it is non-empty when needed.

        Generate a key:
            python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
        """
        if (
            self.platform_auth_mode == "jwt" or self.tenant_auth_mode == "jwt"
        ) and not self.jwt_kek:
            raise ValueError(
                "JWT_KEK must be set when PLATFORM_AUTH_MODE or TENANT_AUTH_MODE is 'jwt'. "
                "Generate with: "
                "python -c \"import os,base64; print(base64.b64encode(os.urandom(32)).decode())\""
            )
        return self
```

- [ ] **Step 4: Run the new config tests**

```bash
pytest tests/core/test_config.py -v
```

Expected: all tests PASS including the updated `test_jwt_kek_validator_accepts_empty_string`

- [ ] **Step 5: Confirm test suite is not broken by the default flip**

```bash
pytest tests/ -v
```

Expected: all tests PASS. The conftest `setdefault` calls keep the test env on stub mode, so the model validator never fires during the test run.

If any test fails with `ValidationError: JWT_KEK must be set`, that test is constructing `Settings(...)` directly with a jwt-mode auth value without passing a valid `jwt_kek`. Fix those calls by either adding `jwt_kek=_VALID_KEK` or adding `platform_auth_mode="stub", tenant_auth_mode="stub"`.

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py tests/core/test_config.py
git commit -m "feat(iam): flip auth mode defaults to jwt; enforce JWT_KEK at settings-load time"
```

---

### Task 2: Complete `.env.example`

**Files:**
- Overwrite: `.env.example`

No failing test required — this is a documentation/configuration file. Verify it is syntactically valid shell by running `env -i sh -c '. .env.example && echo OK'` — it should print OK.

- [ ] **Step 1: Overwrite `.env.example`**

```bash
# .env.example — copy to .env and fill in real values before starting the app.
# NEVER commit .env to version control.

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5432/sacco

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379/0

# ── RabbitMQ ──────────────────────────────────────────────────────────────────
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

# ── Elasticsearch ─────────────────────────────────────────────────────────────
ELASTICSEARCH_URL=http://localhost:9200

# ── App ───────────────────────────────────────────────────────────────────────
# REQUIRED: random 32+ byte string used for HMAC password-reset tokens.
# Generate: python -c "import secrets; print(secrets.token_hex(32))"
APP_SECRET_KEY=CHANGE_ME_IN_PRODUCTION

APP_ENV=development
LOG_LEVEL=INFO
# JSON array: ["http://localhost:3000","http://localhost:8080"]
ALLOWED_ORIGINS=["http://localhost:3000"]

# ── DB pool ───────────────────────────────────────────────────────────────────
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# ── Observability ─────────────────────────────────────────────────────────────
# Set to true in production to emit JSON logs
STRUCTLOG_JSON=false
SLOW_QUERY_MS=200

# ── Headers ───────────────────────────────────────────────────────────────────
REQUEST_ID_HEADER=X-Request-ID
TENANT_HEADER=X-Tenant-Slug

# ── Platform auth ─────────────────────────────────────────────────────────────
# "jwt" (default) uses RS256 JWT tokens via the IAM signing key infrastructure.
# "stub" bypasses cryptographic auth — DEV ONLY, forbidden in APP_ENV=production.
PLATFORM_AUTH_MODE=jwt

PLATFORM_BOOTSTRAP_EMAIL=admin@yoursacco.org
PLATFORM_BOOTSTRAP_FULL_NAME=Platform Admin

# ── Tenant auth ───────────────────────────────────────────────────────────────
# "jwt" (default) uses RS256 JWT tokens with audience "tenant:<slug>".
# "stub" bypasses cryptographic auth — DEV ONLY, forbidden in APP_ENV=production.
TENANT_AUTH_MODE=jwt

# ── JWT signing key infrastructure ────────────────────────────────────────────
# REQUIRED when PLATFORM_AUTH_MODE=jwt or TENANT_AUTH_MODE=jwt.
# Key-encryption-key (KEK) used to encrypt RSA private keys at rest in the DB.
# Must be a base64-encoded 32-byte random value.
# Generate: python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
JWT_KEK=CHANGE_ME_IN_PRODUCTION

# How many days before a signing key is rotated (default 90).
JWT_KEY_ROTATION_DAYS=90

# Access token lifetime in seconds (default 900 = 15 min).
JWT_ACCESS_TTL_SECONDS=900

# Refresh token lifetime for platform (admin) sessions, in seconds (default 3600 = 1 h).
JWT_REFRESH_TTL_PLATFORM_SECONDS=3600

# Refresh token lifetime for tenant (member) sessions, in seconds (default 28800 = 8 h).
JWT_REFRESH_TTL_TENANT_SECONDS=28800

# ── Password policy ───────────────────────────────────────────────────────────
# Minimum password length enforced by hash_password(). Default: 12.
AUTH_PASSWORD_MIN_LENGTH=12

# ── Login lockout (Redis-backed) ──────────────────────────────────────────────
# Number of consecutive failed login attempts before the account is locked.
AUTH_LOCKOUT_THRESHOLD=5

# Sliding window (minutes) over which failed attempts are counted.
AUTH_LOCKOUT_WINDOW_MINUTES=15

# How long (minutes) the account stays locked after threshold is reached.
AUTH_LOCKOUT_DURATION_MINUTES=30

# ── Outbox retention ──────────────────────────────────────────────────────────
OUTBOX_RETENTION_DAYS=90
```

- [ ] **Step 2: Verify the file is valid shell**

```bash
env -i sh -c 'set -a; . .env.example; set +a; echo OK'
```

Expected: `OK` (no parse errors). If any line fails, fix the quoting — most common issue is JSON arrays; they must be quoted: `ALLOWED_ORIGINS='["http://localhost:3000"]'`.

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "docs: complete .env.example with all IAM variables (jwt mode, KEK, lockout, ttls)"
```

---

### Task 3: CLAUDE.md — IAM module contracts

**Files:**
- Modify: `CLAUDE.md`

No failing test required — this is documentation.

- [ ] **Step 1: Update the Platform_ module contracts note**

Find the line:

```
- Platform auth is a stub. get_current_platform_user validates X-Platform-Actor-ID against platform.platform_users but does NOT authenticate. Production deployment requires PLATFORM_AUTH_MODE != stub (enforced at startup).
```

Replace it with:

```
- Platform auth uses RS256 JWT tokens when PLATFORM_AUTH_MODE=jwt (default). The stub (X-Platform-Actor-ID header, no crypto) requires PLATFORM_AUTH_MODE=stub and is forbidden in production. Do not add password or login logic to platform_/ — that belongs in IAM.
```

- [ ] **Step 2: Add IAM contracts section to CLAUDE.md**

Append after the "Platform_ module contracts (do not violate)" section:

```markdown
## IAM module contracts (do not violate)

- `PLATFORM_AUTH_MODE=jwt` and `TENANT_AUTH_MODE=jwt` are the production defaults. `stub` mode requires explicit opt-in and is forbidden when `APP_ENV=production`.
- `JWT_KEK` must be a base64-encoded 32-byte key-encryption-key. It is required at `Settings()` construction time whenever either auth mode is `jwt`. Never hardcode a KEK.
- `verify_boot_keys()` is called at startup when either auth mode is `jwt`. Do not remove or bypass this call.
- RSA signing keys are rotated by the Celery beat job (`rotate_signing_keys_if_due`). Do not create or delete signing key rows directly — use `KeyService`.
- Session revocation is immediate: `SessionService.is_jti_valid` checks Redis on every token decode. Do not skip this check in auth dependencies.
- Lockout is enforced only at the login endpoint (`PlatformAuthService.login`, `TenantAuthService.login`). Do not add lockout checks to the JWT dependency or to token refresh/logout.
- `reset_request()` must always return `None` regardless of whether the email exists. Never reveal user existence via this endpoint (anti-enumeration).
- Password reset tokens are single-use (15-minute TTL). The JTI is stored in Redis and consumed on `reset_confirm()`. Do not skip the Redis jti check when Redis is available.
- All auth operations write to `audit_log` via `write_platform_auth_event` / `write_tenant_auth_event`. Do not remove these calls. For failed login attempts, actor_id may be `None` (unknown user) — the nil UUID is used as record_id in that case.
- JWT token audiences: platform tokens use `aud="platform"`, tenant tokens use `aud="tenant:<slug>"`. A token issued for one tenant is rejected by another tenant's endpoints.
- `CurrentPlatformUser` is exported from `app.platform_.auth`. `CurrentTenantUser` is exported from `app.modules.iam.dependencies`. Do not import the underlying dependency functions directly into route handlers.
```

- [ ] **Step 3: Verify CLAUDE.md renders cleanly**

```bash
python -c "
import re, sys
text = open('CLAUDE.md').read()
# Check no broken markdown headers
headers = re.findall(r'^#{1,3} .+', text, re.MULTILINE)
print(f'{len(headers)} headers found')
# Check IAM section present
assert 'IAM module contracts' in text, 'IAM contracts section missing'
print('CLAUDE.md OK')
"
```

Expected: prints header count and `CLAUDE.md OK`

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add IAM module contracts to CLAUDE.md; update platform_ auth note"
```

---

## Final Verification

- [ ] **Linter and type checker on all IAM modules and config**

```bash
ruff check app/core/config.py app/modules/iam/
mypy app/core/config.py app/modules/iam/ --strict
```

Expected: zero errors

- [ ] **Full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Confirm stub mode is still active in test env**

```bash
pytest -v -k "test_platform_auth_mode_stub_in_test_env or test_tenant_auth_mode_stub_in_test_env"
```

Expected: both PASS (conftest setdefault keeps tests on stub mode)

- [ ] **Confirm production boot would refuse stub**

```python
# Manual spot-check — run in a Python shell, do NOT commit this as a test.
import os
os.environ["APP_ENV"] = "production"
os.environ["PLATFORM_AUTH_MODE"] = "stub"
os.environ["JWT_KEK"] = ""
# If main.py lifespan ran it would raise RuntimeError. Check only config-level:
from app.core.config import Settings
from pydantic import ValidationError
try:
    s = Settings(database_url="x", app_secret_key="y", app_env="production", platform_auth_mode="jwt", tenant_auth_mode="stub", jwt_kek="")
except ValidationError as e:
    print("GOOD — validator caught empty KEK:", e)
```

---

## What Is NOT in This Plan

- **Email notifier for password reset** — `reset_request()` logs tokens to structlog in dev. Wiring a real email provider (SendGrid, Postmark, SMTP) is a future operational task outside IAM v1 scope.
- **Key rotation alerting** — the Celery beat job (`rotate_signing_keys_if_due`) silently rotates keys. Observability (Prometheus metric, PagerDuty alert on rotation failure) is infrastructure-level work.
- **Rate limiting on auth endpoints** — lockout (Plan 10) handles repeated login failures per email. IP-level rate limiting belongs in the reverse proxy (nginx/Traefik), not application code.
- **Multi-factor authentication** — not in IAM v1 scope.
- **Tenant user self-registration** — tenant users are created by platform operators via the tenant user CRUD service (Plan 04). Public signup is a future feature.

---

## IAM v1 Complete

All 12 plans merged. The system now delivers:

| Capability | Plans |
|---|---|
| RS256 JWT signing keys, JWKS endpoint, rotation | 01 |
| argon2id password hashing, policy enforcement | 02 |
| Platform + tenant sessions, Redis revocation | 03 |
| Tenant users, provisioning bootstrap | 04 |
| Platform login / refresh / logout | 05 |
| Tenant login / refresh / logout | 06 |
| /me endpoints (platform + tenant) | 07 |
| Password reset (HMAC token, single-use, 15 min) | 08 |
| Real JWT auth dependencies, auth mode binding switch | 09 |
| Redis-backed login lockout, 423 with Retry-After | 10 |
| Audit events on all 16 auth operations | 11 |
| Production-safe defaults, complete .env, CLAUDE.md | 12 |
