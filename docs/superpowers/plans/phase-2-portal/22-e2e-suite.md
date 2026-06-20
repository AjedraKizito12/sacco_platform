# E2E Test Suite (SP22) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Environment note (2026-06-20):** background subagents can't get Edit approval; run **inline**. This sub-plan needs the **full local stack** (postgres + backend + portal). Test DB / dev DB: the real Postgres is the compose service; `.env` `DATABASE_URL` may be stale (port 5532) — the dev `postgres` service is :5432, `postgres-test` is :5433. The seed targets a **dev** DB the backend also uses. Known host-postgres-port fragility (memory) can break `docker compose up postgres`.

**Goal:** Real browser e2e (login → dashboard → navigate nav groups → list-with-data → logout) against a live seeded backend, extending the existing Playwright setup.

**Architecture:** An idempotent `scripts/e2e_seed.py` creates a signing key + a login-capable platform superuser + one tenant row. A `make admin-e2e` target orchestrates infra + migrations + seed + backend + the Playwright run. A Playwright `global-setup` logs in once and saves `storageState`; authenticated specs reuse it. Smoke specs: auth, navigation, list data.

**Tech Stack:** Python (async SQLAlchemy, IAM services), Playwright (`@playwright/test`), Make, Next.js portal.

---

## Contract & scope notes (read before starting)

- **Dev/test infrastructure**, not pure-client. New backend dev tooling (`scripts/e2e_seed.py`), `Makefile`, Playwright specs/config, `.gitignore`. No `app/` business-logic changes — the seed only calls existing services.
- **Backend facts:** platform login = IAM `PlatformAuthService.login(email,password)` verifying argon2 `hashed_password` (`app/modules/iam/passwords/service.py:hash_password`). JWT mode (default) needs `JWT_KEK` + an active `aud="platform"` signing key; `KeyService(session).generate_and_insert("platform")` mints the first one (KeyService reads `JWT_KEK` from settings). `make migrate` = `alembic upgrade head`. Backend serves :8001; portal reads `NEXT_PUBLIC_API_BASE_URL ?? http://localhost:8001`.
- **Smoke scope only:** auth + navigation + one data assertion per list. Maker-checker / per-screen / tenant-login e2e deferred.
- **Local-first:** CI is environmentally broken; e2e runs locally, does not gate PRs.

## File structure

- Create `scripts/e2e_seed.py`.
- Modify `Makefile` (+ `admin-e2e`, `.PHONY`).
- Modify `admin/apps/portal/playwright.config.ts` (globalSetup + projects + storageState).
- Create `admin/apps/portal/tests/e2e/global-setup.ts`.
- Modify `admin/apps/portal/tests/e2e/auth.spec.ts` (+2 real-login tests).
- Create `admin/apps/portal/tests/e2e/navigation.spec.ts`, `.../data.spec.ts`.
- Modify `.gitignore` (ignore `tests/e2e/.auth/`).

---

## Task 1: `scripts/e2e_seed.py` (idempotent seed)

**Files:**
- Create: `scripts/e2e_seed.py`

- [ ] **Step 1: Confirm model field names** — `rg -n "class PlatformUser" -A 20 app/platform_/models.py` and the tenants model. Confirm `PlatformUser` has `email, full_name, is_active, is_superuser, role, hashed_password, created_at, updated_at`, and the `Tenant` model's required columns (`slug, schema_name, name, status, is_active, created_at, …`). Adjust the script to the real columns.

- [ ] **Step 2: Write the script**

```python
#!/usr/bin/env python3
"""Idempotent seed for portal e2e tests: a signing key, a login-capable
platform superuser, and one active tenant row.

Usage (from project root, with the dev DB + JWT_KEK in env):
    DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5432/sacco \\
    JWT_KEK=<base64-32-bytes> python scripts/e2e_seed.py

Safe to run repeatedly — each step is a no-op when the row already exists.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.modules.iam.keys.models import JwtSigningKey
from app.modules.iam.keys.service import KeyService
from app.modules.iam.passwords.service import hash_password
from app.platform_.models import PlatformUser, Tenant

E2E_EMAIL = os.environ.get("E2E_EMAIL", "e2e@platform.test")
E2E_PASSWORD = os.environ.get("E2E_PASSWORD", "e2e-Password-123!")
E2E_TENANT_SLUG = "e2e-sacco"
E2E_TENANT_SCHEMA = "tenant_e2e_sacco"


async def _seed() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            await session.execute(text("SET search_path TO platform"))

            # 1. Signing key (only if none active for aud=platform).
            active = await session.scalar(
                select(JwtSigningKey).where(
                    JwtSigningKey.audience == "platform",
                    JwtSigningKey.status == "active",
                )
            )
            if active is None:
                await KeyService(session).generate_and_insert("platform")
                print("seed: created platform signing key")
            else:
                print("seed: signing key already present")

            # 2. Superuser.
            user = await session.scalar(
                select(PlatformUser).where(PlatformUser.email == E2E_EMAIL)
            )
            if user is None:
                session.add(
                    PlatformUser(
                        email=E2E_EMAIL,
                        full_name="E2E Operator",
                        hashed_password=hash_password(E2E_PASSWORD),
                        is_active=True,
                        is_superuser=True,
                        role="superuser",
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )
                print(f"seed: created superuser {E2E_EMAIL}")
            else:
                print(f"seed: superuser {E2E_EMAIL} already present")

            # 3. Tenant row (display only — no provisioning).
            tenant = await session.scalar(
                select(Tenant).where(Tenant.slug == E2E_TENANT_SLUG)
            )
            if tenant is None:
                session.add(
                    Tenant(
                        id=uuid.uuid4(),
                        slug=E2E_TENANT_SLUG,
                        schema_name=E2E_TENANT_SCHEMA,
                        name="E2E SACCO",
                        status="active",
                        is_active=True,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )
                print(f"seed: created tenant {E2E_TENANT_SLUG}")
            else:
                print(f"seed: tenant {E2E_TENANT_SLUG} already present")

            await session.commit()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_seed())
```

> Adjust `Tenant(...)` kwargs to the real model (it likely has more required
> columns — `subscription_status`, `seed_version`, etc.; set sensible defaults or
> rely on model defaults). The Step-1 grep tells you exactly. If `Tenant`
> construction needs many fields, prefer a raw `INSERT ... ON CONFLICT DO NOTHING`
> for the tenant row to stay robust against schema additions.

- [ ] **Step 3: Run it (idempotency check)**

Bring up infra + migrate first:
```bash
cd /home/liam/projects/sacco-platform
docker compose up -d postgres
export DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5432/sacco
export JWT_KEK=$(python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())")
alembic upgrade head
python scripts/e2e_seed.py    # creates
python scripts/e2e_seed.py    # all no-ops
```
Expected: first run prints "created …"; second prints "already present" for all three.

> If `docker compose up -d postgres` fails on a host-port clash (memory note),
> use the `postgres-test` service on :5433 + a matching `DATABASE_URL`, or the
> documented `docker-compose.override.yml` `!override` port trick.

- [ ] **Step 4: ruff + mypy on the script**

Run: `ruff check scripts/e2e_seed.py && mypy scripts/e2e_seed.py`
Expected: clean. (Fix imports/types; `scripts/` isn't in the default lint path, so lint it explicitly.)

- [ ] **Step 5: Commit**

```bash
git add scripts/e2e_seed.py
git commit -m "feat(e2e): idempotent seed — signing key + superuser + tenant

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `make admin-e2e` + .gitignore

**Files:**
- Modify: `Makefile`
- Modify: `.gitignore`

- [ ] **Step 1: Add the target** (match the `admin-*` style; read the `.PHONY` line + an existing `admin-*` target first)

```makefile
admin-e2e: ## Seed + run portal Playwright e2e against a local backend
	docker compose up -d postgres redis
	alembic upgrade head
	python scripts/e2e_seed.py
	@echo "Start the backend on :8001 (PLATFORM_AUTH_MODE=jwt, JWT_KEK set), then:"
	@echo "  cd admin && NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 pnpm --filter @sacco/portal e2e"
	cd admin && pnpm --filter @sacco/portal e2e
```

Add `admin-e2e` to the `.PHONY` list. Document in the recipe comment that
`JWT_KEK`, `PLATFORM_AUTH_MODE=jwt`, `DATABASE_URL`, and a running backend on
:8001 are prerequisites (the recipe assumes the backend is started separately or
via `make api` in another shell — keep it readable/overridable rather than
forking a backend process inside Make).

> Decide during execution whether `make admin-e2e` should also background the
> backend (`make api &`) or just document it. Prefer documenting — backgrounding
> uvicorn inside Make is fragile and hard to tear down. The target's job is
> infra + migrate + seed + run; the human (or a future CI job) starts the API.

- [ ] **Step 2: .gitignore** — add:

```
admin/apps/portal/tests/e2e/.auth/
```

- [ ] **Step 3: Commit**

```bash
git add Makefile .gitignore
git commit -m "chore(e2e): admin-e2e make target + gitignore auth state

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Playwright global-setup + config

**Files:**
- Create: `admin/apps/portal/tests/e2e/global-setup.ts`
- Modify: `admin/apps/portal/playwright.config.ts`

- [ ] **Step 1: `global-setup.ts`** — logs in once, saves storageState

```ts
import { chromium, type FullConfig } from "@playwright/test";

const EMAIL = process.env["E2E_EMAIL"] ?? "e2e@platform.test";
const PASSWORD = process.env["E2E_PASSWORD"] ?? "e2e-Password-123!";

export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0]?.use.baseURL ?? "http://localhost:3000";
  const browser = await chromium.launch();
  const page = await browser.newPage({ baseURL });
  await page.goto("/platform/login");
  await page.getByLabel(/email/i).fill(EMAIL);
  await page.getByLabel(/password/i).fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/platform(\/|$)/, { timeout: 15_000 });
  await page.context().storageState({ path: "tests/e2e/.auth/platform.json" });
  await browser.close();
}
```

> Confirm the login form's field labels against `LoginForm` (the `getByLabel`
> matchers). If the inputs aren't label-associated, use `getByRole("textbox",
> {name})` or `name`-based locators. The post-login URL is `/platform` (the
> dashboard); adjust the `waitForURL` regex if it redirects via `?next=`.

- [ ] **Step 2: Wire `playwright.config.ts`**

Add `globalSetup: "./tests/e2e/global-setup.ts"`. Split projects so authenticated
specs use the saved state and the unauth tests don't:

```ts
projects: [
  {
    name: "unauth",
    testMatch: /auth\.spec\.ts/,
    use: { ...devices["Desktop Chrome"], storageState: { cookies: [], origins: [] } },
  },
  {
    name: "authed",
    testIgnore: /auth\.spec\.ts/,
    use: { ...devices["Desktop Chrome"], storageState: "tests/e2e/.auth/platform.json" },
    dependencies: [],
  },
],
```

> `auth.spec.ts` keeps the no-backend tests AND the new real-login tests — both
> run in the `unauth` project (real login starts from a clean state). The
> `authed` project covers navigation + data specs. If `globalSetup` runs even
> when only unauth tests are selected, that's fine (it just logs in); to make the
> no-backend subset runnable without a backend, the plan can gate globalSetup on
> an env flag — keep it simple: globalSetup always runs, the suite assumes the
> stack is up (this is the seeded-stack sub-plan).

- [ ] **Step 3: Validate the specs compile** (no stack needed)

Run: `cd admin && pnpm --filter @sacco/portal exec playwright test --list`
Expected: lists the test titles across projects without a TypeScript error.

- [ ] **Step 4: Commit**

```bash
git add admin/apps/portal/tests/e2e/global-setup.ts admin/apps/portal/playwright.config.ts
git commit -m "feat(e2e): playwright global-setup login + storageState projects

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Specs — auth (real login) + navigation + data

**Files:**
- Modify: `admin/apps/portal/tests/e2e/auth.spec.ts`
- Create: `admin/apps/portal/tests/e2e/navigation.spec.ts`
- Create: `admin/apps/portal/tests/e2e/data.spec.ts`

- [ ] **Step 1: Extend `auth.spec.ts`** (keep the 3 existing tests; add inside the describe)

```ts
test("logs in with seeded credentials and reaches the dashboard", async ({ page }) => {
  await page.goto("/platform/login");
  await page.getByLabel(/email/i).fill(process.env["E2E_EMAIL"] ?? "e2e@platform.test");
  await page.getByLabel(/password/i).fill(process.env["E2E_PASSWORD"] ?? "e2e-Password-123!");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/platform(\/|$)/);
  await expect(page.getByRole("heading", { name: /dashboard|operations|platform/i })).toBeVisible();
});

test("logs out back to the login screen", async ({ page }) => {
  // log in first (unauth project has no stored state)
  await page.goto("/platform/login");
  await page.getByLabel(/email/i).fill(process.env["E2E_EMAIL"] ?? "e2e@platform.test");
  await page.getByLabel(/password/i).fill(process.env["E2E_PASSWORD"] ?? "e2e-Password-123!");
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/platform(\/|$)/);
  // open the user menu and click logout (confirm the actual control names)
  await page.getByRole("button", { name: /account|menu|e2e/i }).click();
  await page.getByRole("menuitem", { name: /log out|sign out/i }).click();
  await expect(page).toHaveURL(/\/platform\/login/);
});
```

> Confirm the dashboard heading text and the user-menu / logout control names
> against the real Shell components (`UserMenu`); adjust the locators. The
> dashboard at `/platform` is the placeholder — assert whatever heading it
> actually renders.

- [ ] **Step 2: `navigation.spec.ts`** (authed project)

```ts
import { test, expect } from "@playwright/test";

const NAV: Array<[string, RegExp]> = [
  ["/platform/tenants", /tenants/i],
  ["/platform/users", /users/i],
  ["/platform/operations", /operations/i],
  ["/platform/settings", /settings/i],
  ["/platform/approvals", /approvals/i],
  ["/platform/audit", /audit/i],
];

test.describe("Platform navigation", () => {
  for (const [path, heading] of NAV) {
    test(`navigates to ${path}`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    });
  }
});
```

> Going directly to each path (storageState keeps us authenticated) is more
> robust than clicking sidebar items. If a heading regex is ambiguous, tighten it
> to the exact `<h1>` text the page renders.

- [ ] **Step 3: `data.spec.ts`** (authed project)

```ts
import { test, expect } from "@playwright/test";

test("users list shows the seeded operator", async ({ page }) => {
  await page.goto("/platform/users");
  await expect(page.getByText(process.env["E2E_EMAIL"] ?? "e2e@platform.test")).toBeVisible();
});

test("tenants list shows the seeded tenant", async ({ page }) => {
  await page.goto("/platform/tenants");
  await expect(page.getByText("E2E SACCO")).toBeVisible();
});
```

- [ ] **Step 4: Validate compile** — `pnpm --filter @sacco/portal exec playwright test --list` (lists all specs, no TS error). Commit.

```bash
git add admin/apps/portal/tests/e2e/
git commit -m "feat(e2e): real-login, navigation, and list-data smoke specs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Full run + PR

- [ ] **Step 1: Run the full stack e2e** (best-effort; document the outcome)

```bash
cd /home/liam/projects/sacco-platform
docker compose up -d postgres redis
export DATABASE_URL=postgresql+asyncpg://sacco:sacco@localhost:5432/sacco
export JWT_KEK=$(python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())")
export PLATFORM_AUTH_MODE=jwt
alembic upgrade head
python scripts/e2e_seed.py
# start backend in another shell: uvicorn app.main:app --port 8001
cd admin && pnpm --filter @sacco/portal e2e:install   # browsers, once
NEXT_PUBLIC_API_BASE_URL=http://localhost:8001 pnpm --filter @sacco/portal e2e
```
Expected: the suite passes (unauth + real-login + navigation + data). **Record
the actual result** — if the local stack can't be fully brought up in this
environment (port fragility, no backend process), report that honestly: the seed
ran, the specs compile (`playwright test --list`), and the full run is documented
for local reproduction. Do not claim green without the run.

- [ ] **Step 2: Keep the non-e2e gates green**

```bash
cd /home/liam/projects/sacco-platform && ruff check scripts/e2e_seed.py && mypy scripts/e2e_seed.py
cd admin && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
(The portal vitest suite is unchanged by e2e files — confirm it still passes if any shared config changed.)

- [ ] **Step 3: Contract spot-checks**

- [ ] Changed paths limited to `scripts/`, `Makefile`, `.gitignore`, `admin/`, `docs/` (`git diff --name-only main...HEAD | grep -vE '^(scripts/|Makefile|\.gitignore|admin/|docs/)'` empty).
- [ ] No `app/` or `tests/` business-logic changes (`git diff --name-only main...HEAD | grep -E '^(app/|tests/)'` empty).

- [ ] **Step 4: Push + PR**

```bash
cd /home/liam/projects/sacco-platform
git push -u origin feat/portal-v1/22-e2e-suite
gh pr create --title "feat(e2e): seeded full-stack Playwright suite (SP22)" --body "$(cat <<'EOF'
## Summary
- Real-backend Playwright e2e: login → dashboard → navigate nav groups → list-with-data → logout, building on the existing config + the 3 no-backend specs.
- `scripts/e2e_seed.py` (idempotent): a platform signing key + a login-capable superuser (`e2e@platform.test`) + one active tenant row — the first login-capable platform bootstrap in the repo.
- `make admin-e2e` orchestrates infra + migrate + seed + the Playwright run; a Playwright `global-setup` logs in once and saves `storageState` for the authenticated specs.

## Scope
- Smoke only: auth + navigation + one data assertion per list. Maker-checker / per-screen / tenant-login e2e deferred.
- **Local-first:** CI Lint is environmentally broken (billing lock); e2e runs locally and does not gate PRs yet.

## Test plan
- `python scripts/e2e_seed.py` runs idempotently (2nd run all no-ops); `ruff`/`mypy` clean on the script.
- `playwright test --list` compiles all specs; full run via `make admin-e2e` (+ backend on :8001) — see PR notes for the local run result.
- No `app/`/`tests/` business-logic changes; portal typecheck/lint green.

> CI note: Lint fails environmentally on this repo (account billing lock); reproduced clean locally. Not a required check.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (author)

- **Spec coverage:** seed script → T1; orchestration + gitignore → T2; global-setup + config → T3; specs → T4; run + PR → T5.
- **Honesty:** T5 Step 1 explicitly requires reporting the real run outcome and forbids claiming green without it — the full stack may not come up cleanly in every environment.
- **Verify-at-execution:** `PlatformUser`/`Tenant` exact columns (T1 Step 1 — use raw INSERT for the tenant if construction is fragile); `LoginForm` field labels + `UserMenu`/logout control names (T3/T4 locators); the real dashboard heading text at `/platform`; whether `globalSetup` should be env-gated so the no-backend subset stays runnable standalone.
- **Type consistency:** `E2E_EMAIL`/`E2E_PASSWORD`/`E2E_TENANT_SLUG` constants + the seeded "E2E SACCO" name are referenced identically across the seed (T1), global-setup (T3), and specs (T4).
