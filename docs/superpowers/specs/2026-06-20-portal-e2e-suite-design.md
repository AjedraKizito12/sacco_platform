# Portal — E2E Test Suite (SP22) Design

**Date:** 2026-06-20
**Phase:** 2 (Admin Portal), sub-plan 22 — the "sub-plan 39" CI/e2e foundation
**Status:** Approved

## Goal

Real browser end-to-end coverage of the portal's authenticated flows
(login → dashboard → navigate the nav groups → list-with-data → logout) against a
**live seeded backend**, building on the existing Playwright config and the three
backend-less specs already in `tests/e2e/auth.spec.ts`.

## Posture (dev/test infrastructure — NOT pure-client)

Unlike SP12–SP21, SP22 is **test/dev infrastructure**: it adds a backend seed
script, Makefile orchestration, and Playwright specs. The portal fetches data
**server-side** (RSC + route handlers), so Playwright cannot browser-mock the
API — a stubbed backend would have to be a real HTTP server. We chose the real
seeded stack for fidelity. This is the Docker-compose e2e foundation the codebase
already anticipated (the deferral note in `auth.spec.ts`). No business logic
changes; the seed only *calls* existing services.

Already in place (verified):

- **Playwright:** `admin/apps/portal/playwright.config.ts` (testDir `./tests/e2e`,
  `webServer: pnpm dev` at :3000, `reuseExistingServer`), `@playwright/test`
  devDep, scripts `e2e` / `e2e:install`. `tests/e2e/auth.spec.ts` has 3
  no-backend tests (unauth redirect, login form renders, client-side validation).
- **Backend login:** IAM `PlatformAuthService.login(email, password)` verifies an
  **argon2** `hashed_password` (`app/modules/iam/passwords/service.py:hash_password`).
  JWT mode (`PLATFORM_AUTH_MODE=jwt`, default) requires `JWT_KEK` + an active
  signing key for `aud="platform"`; `verify_boot_keys()` checks at startup.
- **Signing-key bootstrap:** `KeyService(session).generate_and_insert(audience)`
  — the documented "initial bootstrap only" path (RS256, `status='active'`).
- **Portal config:** server fetches use
  `process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001"`. The
  backend (`make api`) serves on :8001.
- **Makefile:** `admin-*` target convention (`admin-dev`, `admin-test`, …).

## Architecture

### 1. Seed script — `scripts/e2e_seed.py` (idempotent)

A standalone async script (run after platform migrations) that creates exactly
what login + the smoke screens need, each step a no-op if already present:

1. **Signing key** — if no active `aud="platform"` key exists, call
   `KeyService(session).generate_and_insert("platform")`. (KeyService reads
   `JWT_KEK` from settings.)
2. **Platform superuser** — upsert by email `e2e@platform.test`:
   `hashed_password = hash_password(E2E_PASSWORD)` (env, default a fixed dev
   value), `full_name="E2E Operator"`, `is_active=True`, `is_superuser=True`,
   `role="superuser"`. This is the only login-capable platform user bootstrap in
   the repo.
3. **One tenant row** — upsert by slug `e2e-sacco` into `platform.tenants`:
   `status="active"`, `is_active=True`, a valid `schema_name`
   (`tenant_e2e_sacco`), name "E2E SACCO". Direct insert — **no** async
   provisioning (the row is for list/detail *display*, not tenant-schema
   operations).

Credentials live in env with dev defaults: `E2E_EMAIL` (default
`e2e@platform.test`), `E2E_PASSWORD` (default `e2e-Password-123!`). The script
prints what it created/skipped.

> The seed commits in its own transaction(s). It uses the same `AsyncSession` +
> `SET search_path TO platform` pattern as the existing platform code. It must
> NOT create signing keys when one is already active (idempotent), to avoid
> demoting the real key.

### 2. Orchestration — `make admin-e2e`

A Makefile target that runs the full local sequence:

```
admin-e2e:
  1. docker compose up -d postgres redis      # infra (rabbitmq not needed — no provisioning)
  2. alembic -c alembic/platform/alembic.ini upgrade head   # platform migrations
  3. python scripts/e2e_seed.py                # seed superuser + key + tenant
  4. (start backend) uvicorn app.main:app --port 8001  &    # PLATFORM_AUTH_MODE=jwt, JWT_KEK set
  5. cd admin && pnpm --filter @sacco/portal e2e            # Playwright (webServer boots pnpm dev)
```

The target documents the env it needs (`JWT_KEK`, `PLATFORM_AUTH_MODE=jwt`,
`DATABASE_URL`, `NEXT_PUBLIC_API_BASE_URL=http://localhost:8001`). Because the
exact backend-start/teardown is environment-sensitive (the known host-postgres
port fragility), the target is written to be **readable and overridable**, and
the spec documents the manual fallback (start the backend yourself, then `pnpm
--filter @sacco/portal e2e`). The Playwright `webServer` continues to own the
portal dev server.

> The migration command must match the repo's actual alembic invocation — the
> plan confirms it against `alembic/` + existing Makefile `migrate` target.

### 3. Playwright `global-setup.ts` + storageState

`playwright.config.ts` gains `globalSetup: "./tests/e2e/global-setup.ts"` and the
authenticated project sets `use.storageState`. Global-setup:

1. Launches a browser, goes to `/platform/login`, fills `E2E_EMAIL` /
   `E2E_PASSWORD`, submits, waits for the dashboard.
2. Saves `context.storageState()` to `tests/e2e/.auth/platform.json` (gitignored).

Authenticated specs run with `storageState: tests/e2e/.auth/platform.json` — the
saved httpOnly refresh cookie means each spec loads already-authenticated (the
portal refreshes → access token → renders). The unauth specs run **without**
storageState (a separate project or `test.use({ storageState: { cookies: [],
origins: [] } })`).

### 4. Specs

- **`auth.spec.ts`** — keep the 3 existing no-backend tests. Add (real backend):
  - login with seeded creds → redirected to `/platform` and the dashboard
    heading is visible.
  - logout (via the user menu) → back at `/platform/login`.
- **`navigation.spec.ts`** (authenticated, storageState) — from the dashboard,
  click each sidebar item and assert the destination heading:
  Tenants → "Tenants", Users → "Users"/"Platform users", Operations →
  "Operations", Settings → "Settings", Approvals → "Approvals", Audit → "Audit".
- **`data.spec.ts`** (authenticated) — Users list contains `e2e@platform.test`;
  Tenants list contains "E2E SACCO".

Assertions target stable, human-visible text (headings, the seeded email/tenant
name) — not brittle selectors.

## File structure

- Create `scripts/e2e_seed.py`.
- Modify `Makefile` — add `admin-e2e` (+ `.PHONY`).
- Modify `admin/apps/portal/playwright.config.ts` — `globalSetup` + an
  authenticated project with `storageState`, and keep an unauth project.
- Create `admin/apps/portal/tests/e2e/global-setup.ts`.
- Modify `admin/apps/portal/tests/e2e/auth.spec.ts` — add the 2 real-login tests
  (unauth project).
- Create `admin/apps/portal/tests/e2e/navigation.spec.ts`,
  `admin/apps/portal/tests/e2e/data.spec.ts`.
- Modify `.gitignore` — ignore `admin/apps/portal/tests/e2e/.auth/`.

## Known friction (called out honestly)

- **Local-first, not CI-gating yet** — CI Lint is environmentally broken (account
  billing lock); these e2e tests are runnable locally and document the path to CI
  later. They do not block PRs.
- **Orchestration is environment-sensitive** — the host-postgres-on-5432 issue
  (documented in project memory) can break `docker compose up postgres`; the
  spec/plan note the override workaround.
- **Flake is expected** at the stack level; the smoke scope is kept small to
  limit surface.

## Out of scope (deferred)

- **Maker-checker e2e flows** (quorum-2, multi-user approve/reject) — need much
  more seeding; deferred.
- **Per-screen / form-submission e2e** — the smoke suite asserts navigation +
  list data, not every CRUD path.
- **Tenant-scoped portal e2e** (tenant login) — platform only for v1.
- **CI wiring** of e2e (GitHub Actions) — blocked on the CI billing situation.
- **Visual regression / a11y automation** — separate concern.

## Testing strategy

This sub-plan *is* tests. Verification is: `python scripts/e2e_seed.py` runs
idempotently (run twice, second is all no-ops); `make admin-e2e` (or the manual
fallback) runs the Playwright suite green against the seeded stack; the existing
Vitest/typecheck/lint gates stay green (the new files are e2e specs + a Python
script — run `ruff check scripts/e2e_seed.py` and `mypy scripts/e2e_seed.py`
explicitly, since the default `ruff check app/ tests/` does not cover `scripts/`).
Because the e2e run needs the
full stack, the **plan documents** the exact run commands and expected output; a
reviewer can reproduce locally.
