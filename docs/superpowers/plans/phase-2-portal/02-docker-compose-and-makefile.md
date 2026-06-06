# Portal v1 Sub-Plan 02: Docker Compose + Makefile Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/portal-v1/02-compose-makefile` from `main` (or rebase on top of sub-plan 01 if it hasn't merged yet).

**Goal:** Wire the `admin/` workspace into the project's dev ergonomics. After this sub-plan merges, every common admin operation runs via `make admin-*` and the admin dev server is reachable via `docker compose up admin`. **No Next.js code yet** — sub-plan 03 lands the app and the targets here will start doing useful work then.

**Architecture:**
- Append an `admin` service to `docker-compose.yml`. Image is `node:22-slim`; the working directory mounts `./admin/`. The container runs `pnpm install && pnpm dev` on start. No new ports volumes — Next.js will bind 3000 inside the container; we publish it as host 3000 so the operator can hit `http://localhost:3000` once the app exists.
- Six new Makefile targets: `admin-dev`, `admin-build`, `admin-test`, `admin-lint`, `admin-typecheck`, `admin-storybook`. Each delegates to the corresponding pnpm script inside `admin/`. They run on the host (not in the compose service) for fast iteration; the compose service is for "I want a clean, reproducible env" cases.
- Append admin-specific entries to the root `.gitignore` so a clean checkout doesn't surface Turborepo / pnpm / Next.js artefacts.
- Create `admin/.env.example` listing the four environment variables the portal will eventually consume.

**Tech Stack:** Docker Compose, GNU Make, pnpm.

**Portal v1 index reference:** `docs/superpowers/plans/2026-06-02-portal-v1-index.md` §Sub-plan 02.

**Prerequisite:** **Sub-plan 01 must be merged** (or rebased onto). The Makefile targets reference `cd admin && pnpm ...` paths that don't exist without 01's workspace bootstrap.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `docker-compose.yml` | Modify | Append `admin` service (node:22-slim, dev mode) |
| `Makefile` | Modify | Append six `admin-*` targets |
| `.gitignore` | Modify | Append admin-specific ignores |
| `admin/.env.example` | Create | Document the four portal env vars |

---

## Task 1: Root `.gitignore` admin entries

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Append admin entries**

Open `.gitignore`. Append a new section at the end:

```
# ── Admin portal (pnpm + Turborepo + Next.js) ───────────────────────────────
admin/node_modules/
admin/.pnpm-store/
admin/.turbo/
admin/.next/
admin/out/
admin/.vercel/
admin/storybook-static/
admin/**/dist/
admin/**/*.tsbuildinfo
admin/coverage/
```

Note: `admin/.gitignore` (created in sub-plan 01) also lists these — the root entry is the authoritative one for git itself; the admin-local file is for tooling that ignores nested `.gitignore` files.

- [ ] **Step 2: Verify**

```bash
git check-ignore -v admin/node_modules/foo
```
Expected: matches the new pattern.

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore(gitignore): admin portal artefact paths"
```

---

## Task 2: docker-compose.yml `admin` service

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Append the `admin` service block**

Open `docker-compose.yml`. Append the new service definition AFTER the existing `api:` block (keeping the alphabetised-by-purpose order: infra → app):

```yaml
  admin:
    # Next.js 15 portal — dev-mode container. The host's admin/ tree is
    # volume-mounted so live reload works; node_modules stays inside the
    # container to avoid host/container architecture mismatches.
    image: node:22-slim
    restart: unless-stopped
    networks: [sacco_net]
    working_dir: /admin
    ports:
      - "3000:3000"  # Next.js dev server
      - "6006:6006"  # Storybook (sub-plan 04)
    volumes:
      - ./admin:/admin
      - admin_node_modules:/admin/node_modules
    environment:
      # Inside the docker network, the API is reachable at http://api:8000.
      # Host browsers hit it via http://localhost:8000 (or 8001 if API_PORT
      # was overridden — see Makefile).
      NEXT_PUBLIC_API_BASE_URL: "http://localhost:8001"
      # Cookie secret picked up by Next.js middleware (sub-plan 07). Override
      # in a real .env if you want stable sessions across container restarts.
      COOKIE_SECRET: "dev-only-do-not-use-in-production"
      REFRESH_COOKIE_NAME: "sacco_refresh"
    command:
      - sh
      - -c
      - |
        corepack enable && \
        pnpm install --frozen-lockfile && \
        pnpm dev
    depends_on:
      api:
        condition: service_started
```

Add the matching named volume to the top-level `volumes:` block:

```yaml
volumes:
  pgdata:
  redisdata:
  rabbitmqdata:
  esdata:
  admin_node_modules:
```

- [ ] **Step 2: Validate the compose file**

```bash
docker compose config -q
```
Expected: exits 0 (no validation errors).

- [ ] **Step 3: Smoke-build (will spin up, install deps, then sit idle because no Next.js app exists yet)**

```bash
docker compose up -d admin
docker compose logs admin --tail 50
docker compose down admin
```
Expected: container starts; logs show `pnpm install` completing; the `pnpm dev` step prints "No tasks were executed as part of this run." (Turborepo has no `dev` task in any package yet). This is the expected behaviour until sub-plan 03 adds `apps/portal`.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(compose): admin portal service (dev mode)"
```

---

## Task 3: Makefile `admin-*` targets

**Files:**
- Modify: `Makefile`

- [ ] **Step 1: Append the targets**

Open `Makefile`. Find the existing `.PHONY` block at the top (around line 22). Add the new target names:

```makefile
.PHONY: help up down api worker beat migrate seed-defaults seed-demo \
        materialize-reports test test-fast lint mypy ci provision-tenant \
        platform-token tail-api tail-worker \
        admin-install admin-dev admin-build admin-test admin-lint \
        admin-typecheck admin-storybook admin-clean
```

Append a new section AT THE END of the file (after `tail-worker`):

```makefile
# ── Admin portal (Next.js 15) ────────────────────────────────────────────────
#
# All targets run on the host using the local Node 22 toolchain (see
# admin/.nvmrc). For a sealed, reproducible environment use
# `docker compose up admin` instead.

admin-install: ## Install pnpm workspace deps in admin/
	cd admin && pnpm install

admin-dev: ## Run all admin dev servers (Next.js, Storybook) in parallel
	cd admin && pnpm dev

admin-build: ## Production build for every admin package
	cd admin && pnpm build

admin-test: ## Vitest across the admin workspace
	cd admin && pnpm test

admin-lint: ## ESLint across the admin workspace
	cd admin && pnpm lint

admin-typecheck: ## TypeScript no-emit check across the admin workspace
	cd admin && pnpm typecheck

admin-storybook: ## Run Storybook against packages/ui (sub-plan 04)
	cd admin && pnpm --filter @sacco/ui storybook

admin-clean: ## Remove node_modules, .turbo, .next, dist/, storybook-static/
	cd admin && pnpm clean
```

- [ ] **Step 2: Verify**

```bash
make help | grep '^  admin'
```
Expected: every `admin-*` target appears in the help output.

```bash
make admin-typecheck
```
Expected: succeeds (Turborepo no-op because no packages have a `typecheck` script yet).

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "feat(make): admin-* portal targets"
```

---

## Task 4: `admin/.env.example`

**Files:**
- Create: `admin/.env.example`

- [ ] **Step 1: Write the example env file**

```bash
# admin/.env.example — copy to admin/.env.local during development.
# DO NOT commit admin/.env.local.

# ── Backend API ──────────────────────────────────────────────────────────────
# Default points at the host-published API port (see root Makefile API_PORT).
# In production this is the public API origin (https://api.sacco.example).
NEXT_PUBLIC_API_BASE_URL=http://localhost:8001

# ── Observability (sub-plan 40) ──────────────────────────────────────────────
# Public DSN — safe to expose in the browser bundle.
NEXT_PUBLIC_SENTRY_DSN=

# ── Auth shell (sub-plan 07) ─────────────────────────────────────────────────
# 32-byte random secret used to sign the refresh-token cookie envelope.
# Generate: openssl rand -hex 32
COOKIE_SECRET=

# Cookie name used to carry the refresh token. Same value across environments
# so the auth shell middleware can find it consistently.
REFRESH_COOKIE_NAME=sacco_refresh
```

- [ ] **Step 2: Commit**

```bash
git add admin/.env.example
git commit -m "feat(admin): .env.example with portal env vars"
```

---

## Task 5: Final verification

- [ ] **Step 1: Run every new make target as a smoke check**

```bash
make admin-install
make admin-typecheck
make admin-lint
make admin-test
```
Expected: each succeeds. `admin-test` and other Turborepo-driven targets report "no tasks executed" because no packages have those scripts yet — that's the expected state until sub-plan 03 adds `apps/portal`.

- [ ] **Step 2: Verify Docker Compose service config validates**

```bash
docker compose config admin --quiet && echo "compose admin: OK"
```
Expected: prints `compose admin: OK`.

- [ ] **Step 3: Quick smoke of the compose service (optional, slower)**

```bash
docker compose up -d admin
sleep 10
docker compose logs admin --tail 30 | grep -E "(pnpm|Turbo)" | head -10
docker compose down admin
```
Expected: log lines show pnpm and Turborepo running. The compose service won't serve HTTP until sub-plan 03 adds the Next.js app.

- [ ] **Step 4: Confirm root `.gitignore` excludes admin artefacts**

```bash
mkdir -p admin/.next admin/.turbo
git status --short | grep -E "\.(next|turbo)"
```
Expected: empty output (those paths are ignored). Clean up:

```bash
rmdir admin/.next admin/.turbo
```

- [ ] **Step 5: PR**

```bash
git push -u origin feat/portal-v1/02-compose-makefile
gh pr create --title "feat(admin): docker-compose + Makefile integration" --body "$(cat <<'EOF'
## Summary
- New `admin` service in `docker-compose.yml` (node:22-slim, dev mode, ports 3000 + 6006)
- Six new Makefile targets: `admin-install`, `admin-dev`, `admin-build`, `admin-test`, `admin-lint`, `admin-typecheck`, `admin-storybook`, `admin-clean`
- Root `.gitignore` excludes admin Turborepo / pnpm / Next.js / Storybook artefacts
- `admin/.env.example` documents `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SENTRY_DSN`, `COOKIE_SECRET`, `REFRESH_COOKIE_NAME`

## Out of scope
- Next.js app scaffold (sub-plan 03)
- Real Dockerfile for production builds (sub-plan 39 CI/CD)
- Prettier + Husky + lint-staged (sub-plan 03)

## Test plan
- [ ] `make admin-install` succeeds
- [ ] `make admin-typecheck` exits 0 (Turborepo no-op until 03)
- [ ] `make admin-lint` exits 0 (same)
- [ ] `docker compose config admin --quiet` validates
- [ ] `docker compose up -d admin && docker compose logs admin --tail 30` shows pnpm + Turborepo running

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] `docker-compose.yml` declares an `admin` service that boots with `pnpm install && pnpm dev`
- [ ] Root `.gitignore` excludes `admin/node_modules/`, `.turbo/`, `.next/`, `dist/`, `storybook-static/`, and `*.tsbuildinfo`
- [ ] `Makefile` exposes `admin-install`, `admin-dev`, `admin-build`, `admin-test`, `admin-lint`, `admin-typecheck`, `admin-storybook`, `admin-clean` targets, all appearing in `make help`
- [ ] `admin/.env.example` documents the four env vars
- [ ] `make admin-install` and `make admin-typecheck` exit 0 against the empty workspace
- [ ] `docker compose config admin --quiet` validates
- [ ] PR opened, CI green

## Notes for the executing subagent

- **Do not** scaffold the Next.js app here. Sub-plan 03 owns that. If a target needs the app to exist, leave it as a no-op now and document the expected behaviour after 03.
- **Do not** add a Dockerfile in `admin/`. The compose service uses the upstream `node:22-slim` image directly. Sub-plan 39 (CI/CD) will introduce a multi-stage Dockerfile if production needs one.
- **Do not** modify the backend `api`, `postgres`, `redis`, `rabbitmq`, or `elasticsearch` services. The admin service is purely additive.
- **Do not** publish the admin container's ports as `0.0.0.0:` — the default `3000:3000` is fine for dev. Production publishing belongs to the deployment manifest, not this dev compose.
- The `admin_node_modules` named volume is critical: without it, the host's `admin/node_modules` (built for host arch) would shadow the container's install (Linux x86_64), causing native-module crashes. Verify the named volume is declared at the top-level `volumes:` block, not inside the service definition.
- `COOKIE_SECRET` in the compose env is the dev-only literal string. Real environments override via `admin/.env.local` or container orchestrator secrets. Document this in CLAUDE.md only if it becomes a recurring source of confusion — for now the comment in the compose file is enough.
- If `docker compose up admin` fails with "pnpm: not found", the `corepack enable` step in `command:` didn't run — check the YAML block-scalar indentation. The pipe (`|`) is required.
- `make admin-storybook` references `pnpm --filter @sacco/ui storybook`, which won't exist until sub-plan 04. Running it now exits with a clear error from pnpm ("No projects matched the filters"). That's the expected forward-compatibility behaviour.
- If the executing environment doesn't have Docker, every `docker compose` step in the verification block can be skipped — the Makefile targets are the primary contract; compose is the secondary "reproducible env" affordance.
