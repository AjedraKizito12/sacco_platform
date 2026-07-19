# Hetzner Staging Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a reproducible, HTTPS, full-stack staging environment for the SACCO platform on a single Hetzner CPX41, deployable by `git pull` + `docker compose` on the server.

**Architecture:** One VPS runs the whole stack in Docker Compose on an internal network. Caddy is the only host-exposed service (80/443) and auto-provisions Let's Encrypt TLS for two subdomains: the Next.js admin portal (production build) and the FastAPI API. Celery worker + beat run the background jobs; a one-shot `migrate` service applies Alembic migrations before app containers start. Postgres/Redis/RabbitMQ/Elasticsearch are internal-only with named-volume persistence.

**Tech Stack:** Docker Compose, Caddy 2, Python 3.11 / FastAPI / Celery (existing `Dockerfile`), Next.js 15 standalone (new portal Dockerfile), pnpm 9.12 / Node 22, Postgres 16, Redis 7, RabbitMQ 3.12, Elasticsearch 8.17.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-16-staging-deployment-design.md`.
- **Leave the dev `docker-compose.yml` untouched** — staging is a separate `docker-compose.staging.yml`.
- **Only Caddy binds host ports** (80, 443). No other service publishes a host port in staging.
- **`.env.staging` is never committed.** Only `.env.staging.example` (placeholders) is committed. Real secrets are generated on the server.
- **`APP_ENV=production`** in staging → boot guard forbids `stub` auth modes; all auth modes must be `jwt`.
- **`JWT_KEK`** must be base64-encoded 32 random bytes. **`COOKIE_SECRET`** must be random (never the dev `dev-only-do-not-use-in-production`).
- **Single source of truth for the API origin:** portal build-arg `NEXT_PUBLIC_API_BASE_URL` and API `ALLOWED_ORIGINS` must both name `https://api-staging.<domain>` / `https://staging.<domain>` respectively.
- **Celery app:** `app.workers.celery_app` (worker: `celery -A app.workers.celery_app worker`; beat: `... beat`).
- **Node/pnpm:** `node:22-slim`, `pnpm@9.12.0` via corepack. Portal already has `output: "standalone"` in `next.config.mjs`.
- **CLAUDE.md contract N:** infra files at repo root (compose, Caddyfile, deploy scripts, docs, seed script) + Makefile targets are the sanctioned surface for this work. Do NOT touch `app/` business logic, alembic, or module boundaries. The only `app`-adjacent additions are a standalone seed **script** and its test.
- Commit after every task. Use `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` trailers per repo convention.

## File Structure

| Path | New/Mod | Responsibility |
|---|---|---|
| `admin/apps/portal/next.config.mjs` | Modify | CSP `connect-src` from `NEXT_PUBLIC_API_BASE_URL`; drop `unsafe-eval` in prod |
| `admin/apps/portal/Dockerfile` | Create | Multistage Next standalone production image |
| `admin/.dockerignore` | Create | Keep `node_modules`/`.next`/`.turbo` out of the build context |
| `.env.staging.example` | Create | Documented env template for staging |
| `scripts/gen_staging_env.sh` | Create | Generate `.env.staging` with strong random secrets |
| `.gitignore` | Modify | Ignore `.env.staging`, Caddy data |
| `docker-compose.staging.yml` | Create | Full staging topology (datastores + api + worker + beat + migrate + portal + caddy) |
| `Caddyfile` | Create | Reverse-proxy + auto-TLS for both subdomains |
| `scripts/seed_platform_admin.py` | Create | Create a login-capable platform superuser |
| `tests/platform_/users/test_seed_admin.py` | Create | Test the seed function |
| `scripts/deploy.sh` | Create | `git pull` → build → migrate → up |
| `Makefile` | Modify | `staging-*` / `deploy` targets |
| `docs/deployment/hetzner-staging-runbook.md` | Create | One-time provisioning runbook |

---

### Task 1: Portal production image + configurable CSP

**Files:**
- Modify: `admin/apps/portal/next.config.mjs`
- Create: `admin/apps/portal/Dockerfile`
- Create: `admin/.dockerignore`

**Interfaces:**
- Consumes: build arg `NEXT_PUBLIC_API_BASE_URL` (a full origin, e.g. `https://api-staging.example.com`).
- Produces: a Docker image that serves the portal on `:3000` with `node apps/portal/server.js`; its `Content-Security-Policy` header `connect-src` includes `'self'` + the API origin and, in production, omits `'unsafe-eval'`.

- [x] **Step 1: Make the CSP connect-src configurable.** In `admin/apps/portal/next.config.mjs`, replace the hardcoded `connect-src` array and the static `script-src` with env-aware logic. Change the top of the file:

```javascript
/** @type {import('next').NextConfig} */
const isProd = process.env.NODE_ENV === "production";
const apiOrigin = process.env.NEXT_PUBLIC_API_BASE_URL;

const connectSrc = ["'self'"];
if (apiOrigin) {
  connectSrc.push(apiOrigin);
} else {
  // Local dev fallback: the API runs on the host, ports 8000/8001.
  connectSrc.push("http://localhost:8000", "http://localhost:8001", "ws://localhost:3000");
}

const cspDirectives = {
  "default-src": ["'self'"],
  // Dev needs unsafe-eval for HMR; production drops it.
  "script-src": isProd ? ["'self'", "'unsafe-inline'"] : ["'self'", "'unsafe-eval'", "'unsafe-inline'"],
  "style-src": ["'self'", "'unsafe-inline'"],
  "img-src": ["'self'", "data:", "blob:"],
  "font-src": ["'self'"],
  "connect-src": connectSrc,
  "frame-ancestors": ["'none'"],
  "form-action": ["'self'"],
  "base-uri": ["'self'"],
  "object-src": ["'none'"],
};
```

Leave the rest of the file (`cspString`, `nextConfig`, `headers()`) unchanged.

- [x] **Step 2: Verify dev behavior is unchanged.** Run:

```bash
cd admin && NODE_ENV=development node -e "import('./apps/portal/next.config.mjs').then(m => process.stdout.write(JSON.stringify(m.default.headers().then?'':'')))" 2>/dev/null; \
grep -n "connect-src" apps/portal/next.config.mjs
```

Expected: file parses; dev fallback path present. (A full behavioral check happens in Step 6.)

- [x] **Step 3: Create `admin/.dockerignore`:**

```
node_modules
**/node_modules
.next
**/.next
.turbo
**/.turbo
storybook-static
**/dist
.git
```

- [x] **Step 4: Create `admin/apps/portal/Dockerfile`.** Build context is `admin/`.

```dockerfile
# syntax=docker/dockerfile:1

# ── build stage ───────────────────────────────────────────────────────────────
FROM node:22-slim AS build
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate
WORKDIR /admin

ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

COPY . .
RUN pnpm install --frozen-lockfile
# Next standalone expects a public dir; create it if the app has none.
RUN mkdir -p apps/portal/public && pnpm --filter @sacco/portal build

# ── runtime stage ─────────────────────────────────────────────────────────────
FROM node:22-slim AS runner
WORKDIR /admin
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN groupadd --gid 1001 nodejs && \
    useradd --uid 1001 --gid nodejs --no-create-home --shell /bin/false nextjs

# Standalone output: server + traced node_modules, static assets, public.
COPY --from=build --chown=nextjs:nodejs /admin/apps/portal/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /admin/apps/portal/.next/static ./apps/portal/.next/static
COPY --from=build --chown=nextjs:nodejs /admin/apps/portal/public ./apps/portal/public

USER nextjs
EXPOSE 3000
CMD ["node", "apps/portal/server.js"]
```

- [x] **Step 5: Build the image.** Run:

```bash
cd /home/liam/projects/sacco-platform/admin
docker build -f apps/portal/Dockerfile \
  --build-arg NEXT_PUBLIC_API_BASE_URL=https://api-staging.example.com \
  -t sacco-portal:staging-test .
```

Expected: build completes; final line shows the image tagged. If the build fails on a missing workspace package, confirm `.dockerignore` did not exclude `packages/`.

- [x] **Step 6: Run the image and verify the CSP + render.** Run:

```bash
docker run -d --name portal-test -p 3100:3000 -e API_INTERNAL_URL=http://localhost:8000 sacco-portal:staging-test
sleep 3
curl -s -D - -o /dev/null http://localhost:3100/platform/login | grep -i "content-security-policy"
curl -s -o /dev/null -w "login HTTP %{http_code}\n" http://localhost:3100/platform/login
docker rm -f portal-test
```

Expected: CSP header contains `connect-src 'self' https://api-staging.example.com` and does **not** contain `unsafe-eval`; login route returns `200`. (Server-side API calls will fail without a reachable API — that's fine; we only assert the page renders and the header is correct.)

- [x] **Step 7: Commit.**

```bash
cd /home/liam/projects/sacco-platform
git add admin/apps/portal/next.config.mjs admin/apps/portal/Dockerfile admin/.dockerignore
git commit -m "feat(deploy): production portal image + env-driven CSP"
```

> **Done 2026-07-19.** The portal's production `next build` had never been run
> (dev only) and failed on two pre-existing latent bugs, fixed as part of this
> task:
> 1. `packages/ui/src/globals.css` does `@import "tailwindcss"` but `@sacco/ui`
>    never declared `tailwindcss` — pnpm's strict node_modules couldn't resolve
>    it. Fixed by adding the dep to `admin/packages/ui/package.json` (+ lockfile).
>    Committed separately: `fix(portal): declare tailwindcss dep on @sacco/ui`.
> 2. The Dockerfile set `NODE_ENV=production` before `pnpm install`, so pnpm
>    skipped the devDependency build toolchain (`@tailwindcss/postcss`,
>    `@sacco/tsconfig`, `typescript`) — the latter carries the tsconfig
>    `extends` that defines the `@/*` path alias, so aliases failed too. Fixed
>    with `pnpm install --frozen-lockfile --prod=false` in the Dockerfile.

---

### Task 2: Staging env template + secret generator

**Files:**
- Create: `.env.staging.example`
- Create: `scripts/gen_staging_env.sh`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `.env.staging` (git-ignored) consumed by `docker-compose.staging.yml` via `env_file`, and `STAGING_DOMAIN` consumed by the Caddyfile and portal build. Variable names the compose file relies on: `POSTGRES_PASSWORD`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`, `JWT_KEK`, `COOKIE_SECRET`, `STAGING_DOMAIN`, `DATABASE_URL`, `REDIS_URL`, `RABBITMQ_URL`, `ELASTICSEARCH_URL`, `ALLOWED_ORIGINS`, `APP_ENV`, `PLATFORM_AUTH_MODE`, `TENANT_AUTH_MODE`, `MEMBER_AUTH_MODE`, `NEXT_PUBLIC_API_BASE_URL`, `API_INTERNAL_URL`.

- [ ] **Step 1: Create `.env.staging.example`:**

```bash
# ─────────────────────────────────────────────────────────────────────────────
# Staging environment for the SACCO platform (Hetzner). Copy to .env.staging on
# the server and fill real values (scripts/gen_staging_env.sh generates secrets).
# NEVER commit .env.staging.
# ─────────────────────────────────────────────────────────────────────────────

# Domain (two A-records must point at the VPS: staging.<domain>, api-staging.<domain>)
STAGING_DOMAIN=example.com

# App
APP_ENV=production
LOG_LEVEL=info
STRUCTLOG_JSON=true
PLATFORM_AUTH_MODE=jwt
TENANT_AUTH_MODE=jwt
MEMBER_AUTH_MODE=jwt

# Secrets (generate with scripts/gen_staging_env.sh)
JWT_KEK=REPLACE_ME_base64_32_bytes
COOKIE_SECRET=REPLACE_ME_random
POSTGRES_PASSWORD=REPLACE_ME_random
RABBITMQ_USER=sacco
RABBITMQ_PASSWORD=REPLACE_ME_random

# Datastore URLs (internal Docker network hostnames)
DATABASE_URL=postgresql+asyncpg://sacco:REPLACE_ME_random@postgres:5432/sacco
REDIS_URL=redis://redis:6379/0
RABBITMQ_URL=amqp://sacco:REPLACE_ME_random@rabbitmq:5672//
ELASTICSEARCH_URL=http://elasticsearch:9200

# CORS: the browser origin allowed to call the API
ALLOWED_ORIGINS=https://staging.example.com

# Portal ↔ API wiring
NEXT_PUBLIC_API_BASE_URL=https://api-staging.example.com
API_INTERNAL_URL=http://api:8000
REFRESH_COOKIE_NAME=sacco_refresh
```

- [ ] **Step 2: Verify the app reads `allowed_origins` as a list.** Run:

```bash
cd /home/liam/projects/sacco-platform && grep -n "allowed_origins" app/core/config.py
```

Expected: `allowed_origins: list[str]`. Pydantic settings parse a comma-separated env var into a list; the example uses a single origin (still valid). Note this confirms the env name is `ALLOWED_ORIGINS`.

- [ ] **Step 3: Create `scripts/gen_staging_env.sh`:**

```bash
#!/usr/bin/env bash
# Generate .env.staging from .env.staging.example with strong random secrets.
# Usage: STAGING_DOMAIN=your.tld scripts/gen_staging_env.sh
set -euo pipefail

cd "$(dirname "$0")/.."
OUT=.env.staging
[ -f "$OUT" ] && { echo "ERROR: $OUT already exists; refusing to overwrite." >&2; exit 1; }
: "${STAGING_DOMAIN:?Set STAGING_DOMAIN=your.tld}"

KEK=$(openssl rand -base64 32)
COOKIE=$(openssl rand -hex 32)
PGPW=$(openssl rand -hex 24)
MQPW=$(openssl rand -hex 24)

sed \
  -e "s|^STAGING_DOMAIN=.*|STAGING_DOMAIN=${STAGING_DOMAIN}|" \
  -e "s|^JWT_KEK=.*|JWT_KEK=${KEK}|" \
  -e "s|^COOKIE_SECRET=.*|COOKIE_SECRET=${COOKIE}|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${PGPW}|" \
  -e "s|^RABBITMQ_PASSWORD=.*|RABBITMQ_PASSWORD=${MQPW}|" \
  -e "s|REPLACE_ME_random@postgres|${PGPW}@postgres|" \
  -e "s|REPLACE_ME_random@rabbitmq|${MQPW}@rabbitmq|" \
  -e "s|staging\\.example\\.com|staging.${STAGING_DOMAIN}|g" \
  -e "s|api-staging\\.example\\.com|api-staging.${STAGING_DOMAIN}|g" \
  .env.staging.example > "$OUT"

chmod 600 "$OUT"
echo "Wrote $OUT (mode 600). Review it, then run scripts/deploy.sh."
```

Then `chmod +x scripts/gen_staging_env.sh`.

- [ ] **Step 4: Add gitignore entries.** Append to `.gitignore` under "Secrets / local env":

```
.env.staging
caddy_data/
caddy_config/
```

- [ ] **Step 5: Verify generation produces valid values.** Run:

```bash
cd /home/liam/projects/sacco-platform
STAGING_DOMAIN=example.test scripts/gen_staging_env.sh
grep -E "^(JWT_KEK|COOKIE_SECRET|STAGING_DOMAIN)=" .env.staging
echo "KEK bytes:" && grep '^JWT_KEK=' .env.staging | cut -d= -f2- | base64 -d | wc -c
git check-ignore .env.staging && echo "ignored OK"
rm -f .env.staging   # cleanup the test artifact
```

Expected: `JWT_KEK`/`COOKIE_SECRET` filled with random values, `STAGING_DOMAIN=example.test`, "KEK bytes: 32", ".env.staging" reported ignored.

- [ ] **Step 6: Commit.**

```bash
git add .env.staging.example scripts/gen_staging_env.sh .gitignore
git commit -m "feat(deploy): staging env template + secret generator"
```

---

### Task 3: Staging compose — datastores + api + worker + beat + migrate + portal

**Files:**
- Create: `docker-compose.staging.yml`

**Interfaces:**
- Consumes: `.env.staging` (via `env_file`), the api image from `./Dockerfile`, the portal image from `admin/apps/portal/Dockerfile` (build arg `NEXT_PUBLIC_API_BASE_URL`).
- Produces: services `postgres`, `redis`, `rabbitmq`, `elasticsearch`, `api`, `worker`, `beat`, `migrate`, `portal` on network `sacco_net`; named volumes `pgdata_staging`, `redisdata_staging`, `rabbitmqdata_staging`, `esdata_staging`. No host ports (Caddy is added in Task 4).

- [ ] **Step 1: Create `docker-compose.staging.yml`:**

```yaml
name: sacco-staging

networks:
  sacco_net:

volumes:
  pgdata_staging:
  redisdata_staging:
  rabbitmqdata_staging:
  esdata_staging:

services:
  postgres:
    image: postgres:16
    restart: unless-stopped
    networks: [sacco_net]
    volumes:
      - pgdata_staging:/var/lib/postgresql/data
    environment:
      POSTGRES_USER: sacco
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: sacco
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sacco -d sacco"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7
    restart: unless-stopped
    networks: [sacco_net]
    volumes:
      - redisdata_staging:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 10

  rabbitmq:
    image: rabbitmq:3.12-management
    restart: unless-stopped
    networks: [sacco_net]
    volumes:
      - rabbitmqdata_staging:/var/lib/rabbitmq
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD}
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 10s
      timeout: 10s
      retries: 10

  elasticsearch:
    image: elasticsearch:8.17.0
    restart: unless-stopped
    networks: [sacco_net]
    volumes:
      - esdata_staging:/usr/share/elasticsearch/data
    environment:
      discovery.type: single-node
      xpack.security.enabled: "false"
      ES_JAVA_OPTS: "-Xms1g -Xmx1g"
    healthcheck:
      test: ["CMD-SHELL", "curl -sf http://localhost:9200/_cluster/health | grep -qv '\"status\":\"red\"'"]
      interval: 10s
      timeout: 10s
      retries: 15

  migrate:
    build: .
    image: sacco-api:staging
    restart: "no"
    networks: [sacco_net]
    env_file: .env.staging
    command: ["alembic", "upgrade", "head"]
    depends_on:
      postgres:
        condition: service_healthy

  api:
    build: .
    image: sacco-api:staging
    restart: unless-stopped
    networks: [sacco_net]
    env_file: .env.staging
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
      elasticsearch:
        condition: service_healthy

  worker:
    image: sacco-api:staging
    restart: unless-stopped
    networks: [sacco_net]
    env_file: .env.staging
    command: ["celery", "-A", "app.workers.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
    depends_on:
      rabbitmq:
        condition: service_healthy
      redis:
        condition: service_healthy

  beat:
    image: sacco-api:staging
    restart: unless-stopped
    networks: [sacco_net]
    env_file: .env.staging
    command: ["celery", "-A", "app.workers.celery_app", "beat", "--loglevel=info"]
    depends_on:
      rabbitmq:
        condition: service_healthy

  portal:
    build:
      context: ./admin
      dockerfile: apps/portal/Dockerfile
      args:
        NEXT_PUBLIC_API_BASE_URL: ${NEXT_PUBLIC_API_BASE_URL}
    image: sacco-portal:staging
    restart: unless-stopped
    networks: [sacco_net]
    environment:
      API_INTERNAL_URL: ${API_INTERNAL_URL}
      NEXT_PUBLIC_API_BASE_URL: ${NEXT_PUBLIC_API_BASE_URL}
      REFRESH_COOKIE_NAME: ${REFRESH_COOKIE_NAME}
    depends_on:
      - api
```

Note: `worker`/`beat` reference `image: sacco-api:staging` (no `build:`) so they reuse the image built by `api`/`migrate`. The deploy script builds before `up`.

- [ ] **Step 2: Validate compose config.** Run:

```bash
cd /home/liam/projects/sacco-platform
STAGING_DOMAIN=example.test scripts/gen_staging_env.sh
docker compose -f docker-compose.staging.yml --env-file .env.staging config >/dev/null && echo "compose config OK"
```

Expected: "compose config OK" (no interpolation errors, all `${...}` resolved).

- [ ] **Step 3: Smoke-build the images locally.** Run:

```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging build api portal
```

Expected: both images build (`sacco-api:staging`, `sacco-portal:staging`). This reuses the Task-1 portal build and the existing api `Dockerfile`.

- [ ] **Step 4: Local stack smoke (no Caddy/TLS).** Run:

```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d postgres redis rabbitmq elasticsearch
docker compose -f docker-compose.staging.yml --env-file .env.staging run --rm migrate
docker compose -f docker-compose.staging.yml --env-file .env.staging up -d api worker beat portal
sleep 8
docker compose -f docker-compose.staging.yml --env-file .env.staging exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/readyz').read().decode())"
docker compose -f docker-compose.staging.yml --env-file .env.staging ps
```

Expected: `migrate` exits 0; `/readyz` prints all-`ok`; `worker`/`beat`/`portal` show `Up`.

- [ ] **Step 5: Tear down the smoke stack and clean up.** Run:

```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging down -v
rm -f .env.staging
```

Expected: containers + staging volumes removed; test env file deleted.

- [ ] **Step 6: Commit.**

```bash
git add docker-compose.staging.yml
git commit -m "feat(deploy): staging compose (api, worker, beat, migrate, portal, datastores)"
```

---

### Task 4: Caddy reverse proxy + auto-TLS

**Files:**
- Create: `Caddyfile`
- Modify: `docker-compose.staging.yml` (add `caddy` service + volumes)

**Interfaces:**
- Consumes: `STAGING_DOMAIN` env var; internal services `portal:3000` and `api:8000`.
- Produces: public HTTPS on `staging.${STAGING_DOMAIN}` (→ portal) and `api-staging.${STAGING_DOMAIN}` (→ api); Let's Encrypt certs persisted in `caddy_data` volume.

- [ ] **Step 1: Create `Caddyfile`:**

```
{
	# Set ACME email via CADDY_ACME_EMAIL in .env.staging for expiry notices.
	email {$CADDY_ACME_EMAIL}
}

staging.{$STAGING_DOMAIN} {
	encode gzip
	reverse_proxy portal:3000
}

api-staging.{$STAGING_DOMAIN} {
	encode gzip
	reverse_proxy api:8000
}
```

- [ ] **Step 2: Add `CADDY_ACME_EMAIL` to `.env.staging.example`.** Append under the Domain section:

```
CADDY_ACME_EMAIL=you@example.com
```

- [ ] **Step 3: Add the `caddy` service to `docker-compose.staging.yml`.** Add under `services:`:

```yaml
  caddy:
    image: caddy:2
    restart: unless-stopped
    networks: [sacco_net]
    ports:
      - "80:80"
      - "443:443"
    env_file: .env.staging
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - api
      - portal
```

And add to the top-level `volumes:` block:

```yaml
  caddy_data:
  caddy_config:
```

- [ ] **Step 4: Validate the Caddyfile syntax.** Run:

```bash
cd /home/liam/projects/sacco-platform
docker run --rm -e STAGING_DOMAIN=example.test -e CADDY_ACME_EMAIL=you@example.test \
  -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

Expected: `Valid configuration`.

- [ ] **Step 5: Re-validate the full compose config with Caddy.** Run:

```bash
STAGING_DOMAIN=example.test scripts/gen_staging_env.sh
docker compose -f docker-compose.staging.yml --env-file .env.staging config >/dev/null && echo "compose config OK"
rm -f .env.staging
```

Expected: "compose config OK".

- [ ] **Step 6: Commit.**

```bash
git add Caddyfile docker-compose.staging.yml .env.staging.example
git commit -m "feat(deploy): Caddy reverse proxy + auto-TLS for staging subdomains"
```

---

### Task 5: First-run superuser seed

**Files:**
- Create: `scripts/seed_platform_admin.py`
- Create: `tests/platform_/users/test_seed_admin.py`

**Interfaces:**
- Consumes: `PlatformUserService` (`app.platform_.users.service`), `hash_password` (`app.modules.iam.passwords.service`), `PlatformUser` (`app.platform_.models`).
- Produces: `async def seed_platform_admin(session, *, email, full_name, password, role="superuser") -> PlatformUser` — idempotent by email; sets `hashed_password`; keeps `role`/`is_superuser` in sync. Existing user → updates password + role in place. Returns the user.

- [ ] **Step 1: Write the failing test** at `tests/platform_/users/test_seed_admin.py`. Follow the repo's async integration pattern (real Postgres, `async_sessionmaker` + commit + cleanup — NOT a `flush()`-based fixture):

```python
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.platform_.models import PlatformUser
from app.modules.iam.passwords.service import verify_password
from scripts.seed_platform_admin import seed_platform_admin


@pytest.mark.asyncio
async def test_seed_creates_login_capable_superuser(test_engine):
    email = f"seed-{uuid.uuid4().hex[:8]}@platform.example.com"
    Session = async_sessionmaker(test_engine, expire_on_commit=False)
    async with Session() as s:
        user = await seed_platform_admin(
            s, email=email, full_name="Seed Admin", password="S33d-Password!"
        )
        await s.commit()
        assert user.role == "superuser"
        assert user.is_superuser is True
        assert user.hashed_password is not None
        assert verify_password("S33d-Password!", user.hashed_password)

    # Idempotent: second call updates password in place, no duplicate row.
    async with Session() as s:
        await seed_platform_admin(
            s, email=email, full_name="Seed Admin", password="New-Password!"
        )
        await s.commit()
    async with Session() as s:
        rows = (await s.execute(select(PlatformUser).where(PlatformUser.email == email))).scalars().all()
        assert len(rows) == 1
        assert verify_password("New-Password!", rows[0].hashed_password)

    # cleanup
    async with Session() as s:
        await s.execute(PlatformUser.__table__.delete().where(PlatformUser.email == email))
        await s.commit()
```

> Fixtures: `test_engine` (from `tests/conftest.py`) is the shared async engine. Build a fresh `async_sessionmaker` off it with `commit()` + explicit cleanup — do NOT reuse the `platform_session` fixture here, which is `flush()`-based and won't persist across the sessions this test opens.

- [ ] **Step 2: Run the test to verify it fails.** Run:

```bash
cd /home/liam/projects/sacco-platform
env -u DATABASE_URL pytest tests/platform_/users/test_seed_admin.py -v
```

Expected: FAIL — `ModuleNotFoundError`/`ImportError: cannot import name 'seed_platform_admin'`.

- [ ] **Step 3: Write `scripts/seed_platform_admin.py`:**

```python
"""Create (or reset) a login-capable platform superuser.

PlatformUserService.create intentionally leaves hashed_password NULL, so the
bootstrap admin cannot log into the portal. This seed sets a password directly,
mirroring scripts/e2e_seed.py, and is idempotent by email.

Usage (on the server, inside the api image):
    python scripts/seed_platform_admin.py --email admin@you.tld --full-name "Ops Admin"
The password is read from SEED_ADMIN_PASSWORD or prompted interactively.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.modules.iam.passwords.service import hash_password
from app.platform_.models import PlatformUser


async def seed_platform_admin(
    session: AsyncSession,
    *,
    email: str,
    full_name: str,
    password: str,
    role: str = "superuser",
) -> PlatformUser:
    """Idempotently ensure a platform user with the given email exists, has the
    given role, and can log in with the given password. Returns the user."""
    existing = (
        await session.execute(select(PlatformUser).where(PlatformUser.email == email))
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if existing is None:
        user = PlatformUser(
            email=email,
            full_name=full_name,
            role=role,
            is_superuser=(role == "superuser"),
            is_active=True,
            hashed_password=hash_password(password),
            created_at=now,
            updated_at=now,
        )
        session.add(user)
        await session.flush()
        return user

    existing.full_name = full_name
    existing.role = role
    existing.is_superuser = role == "superuser"
    existing.hashed_password = hash_password(password)
    existing.is_active = True
    existing.updated_at = now
    await session.flush()
    return existing


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Seed a platform superuser")
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", default="Platform Admin")
    parser.add_argument("--role", default="superuser")
    args = parser.parse_args()

    password = os.environ.get("SEED_ADMIN_PASSWORD") or getpass("Password: ")
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 2

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        user = await seed_platform_admin(
            session,
            email=args.email,
            full_name=args.full_name,
            password=password,
            role=args.role,
        )
        await session.commit()
        print(f"Seeded platform user {user.email} (role={user.role}).")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
```

- [ ] **Step 4: Run the test to verify it passes.** Run:

```bash
cd /home/liam/projects/sacco-platform
env -u DATABASE_URL pytest tests/platform_/users/test_seed_admin.py -v
```

Expected: PASS (both assertions — create + idempotent reset).

- [ ] **Step 5: Lint/type-check the new script.** Run:

```bash
ruff check scripts/seed_platform_admin.py && mypy scripts/seed_platform_admin.py
```

Expected: clean (matches repo's ruff + mypy strict gate). Fix any findings.

- [ ] **Step 6: Commit.**

```bash
git add scripts/seed_platform_admin.py tests/platform_/users/test_seed_admin.py
git commit -m "feat(deploy): idempotent platform-superuser seed for first login"
```

---

### Task 6: Deploy script, Make targets, provisioning runbook

**Files:**
- Create: `scripts/deploy.sh`
- Modify: `Makefile`
- Create: `docs/deployment/hetzner-staging-runbook.md`

**Interfaces:**
- Consumes: `.env.staging`, `docker-compose.staging.yml`.
- Produces: `scripts/deploy.sh` (idempotent redeploy) and Make targets `staging-build`, `staging-up`, `staging-down`, `staging-logs`, `staging-seed-admin`, `deploy`.

- [ ] **Step 1: Create `scripts/deploy.sh`:**

```bash
#!/usr/bin/env bash
# Redeploy the SACCO staging stack: pull, build, migrate, restart.
# Run as the deploy user on the VPS, from the repo root.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.staging.yml --env-file .env.staging"

[ -f .env.staging ] || { echo "ERROR: .env.staging missing. Run scripts/gen_staging_env.sh first." >&2; exit 1; }

echo "==> Pulling latest code"
git pull --ff-only

echo "==> Building images"
$COMPOSE build

echo "==> Running migrations"
$COMPOSE run --rm migrate

echo "==> Starting services"
$COMPOSE up -d

echo "==> Status"
$COMPOSE ps
echo "Deploy complete. Portal: https://staging.$(grep '^STAGING_DOMAIN=' .env.staging | cut -d= -f2)"
```

Then `chmod +x scripts/deploy.sh`.

- [ ] **Step 2: Add staging targets to the `Makefile`.** Add a new section at the end, and add the target names to the top `.PHONY` line:

```makefile
# ── Staging deployment ────────────────────────────────────────────────────────
STAGING_COMPOSE := docker compose -f docker-compose.staging.yml --env-file .env.staging

staging-build: ## Build staging images
	$(STAGING_COMPOSE) build

staging-up: ## Start the staging stack
	$(STAGING_COMPOSE) up -d

staging-down: ## Stop the staging stack (keeps volumes)
	$(STAGING_COMPOSE) down

staging-logs: ## Tail staging logs (SVC=api to filter)
	$(STAGING_COMPOSE) logs -f $(SVC)

staging-seed-admin: ## Create a login-capable platform superuser. EMAIL=<email>
	@test -n "$(EMAIL)" || (echo "Usage: make staging-seed-admin EMAIL=admin@you.tld" && exit 2)
	$(STAGING_COMPOSE) run --rm api python scripts/seed_platform_admin.py --email $(EMAIL)

deploy: ## Full redeploy (pull, build, migrate, up)
	scripts/deploy.sh
```

Add `staging-build staging-up staging-down staging-logs staging-seed-admin deploy` to the `.PHONY:` list.

- [ ] **Step 3: Verify scripts and Makefile parse.** Run:

```bash
cd /home/liam/projects/sacco-platform
bash -n scripts/deploy.sh && echo "deploy.sh syntax OK"
bash -n scripts/gen_staging_env.sh && echo "gen_staging_env.sh syntax OK"
make -n staging-build 2>/dev/null | head -1 && echo "make target resolves"
```

Expected: both "syntax OK" lines; the make dry-run prints the compose build command.

- [ ] **Step 4: Create `docs/deployment/hetzner-staging-runbook.md`:**

````markdown
# Hetzner Staging Runbook

One-time provisioning + ongoing deploys for the SACCO staging environment.
Design: `docs/superpowers/specs/2026-07-16-staging-deployment-design.md`.

## 1. Provision the VPS (once)

1. Create a Hetzner **CPX41** (8 vCPU / 16 GB), Ubuntu 24.04.
2. DNS: add two `A` records pointing at the VPS IPv4:
   - `staging.<domain>`
   - `api-staging.<domain>`
3. SSH in as root; create a deploy user and harden SSH:
   ```bash
   adduser --disabled-password --gecos "" deploy
   usermod -aG sudo deploy
   rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
   # disable password + root SSH login in /etc/ssh/sshd_config, then: systemctl reload ssh
   ```
4. Firewall:
   ```bash
   ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
   ```
5. Install Docker Engine + compose plugin (get.docker.com), then
   `usermod -aG docker deploy`.

## 2. First deploy (as `deploy`)

```bash
git clone <repo-url> sacco-platform && cd sacco-platform
STAGING_DOMAIN=<domain> scripts/gen_staging_env.sh
# edit .env.staging: set CADDY_ACME_EMAIL
scripts/deploy.sh
make staging-seed-admin EMAIL=admin@<domain>   # prompts for a password
```

Wait for Caddy to obtain certs (first request to each subdomain triggers ACME),
then open `https://staging.<domain>` and log in with the seeded admin.

## 3. Ongoing deploys

```bash
scripts/deploy.sh    # or: make deploy
```

## 4. Operations

- Logs: `make staging-logs SVC=api` (or `worker`, `beat`, `portal`, `caddy`).
- Reset a superuser password: `make staging-seed-admin EMAIL=<email>`.
- Stop/start: `make staging-down` / `make staging-up`.

## Out of scope (roadmap Phases 4–6)

Automated backups (data is in named volumes only), observability, rate limiting,
CI/CD. Losing the VPS loses staging data until Phase 4 ships.
````

- [ ] **Step 5: Commit.**

```bash
git add scripts/deploy.sh Makefile docs/deployment/hetzner-staging-runbook.md
git commit -m "feat(deploy): deploy script, staging make targets, provisioning runbook"
```

---

## Self-Review Notes

- **Spec coverage:** §2 topology → Tasks 3–4; §3 services → Task 3 (+ Caddy Task 4); §4 config/secrets → Task 2; §5 code changes → Task 1 (CSP + portal Dockerfile), Task 3 (compose), Task 4 (Caddyfile), Task 5 (seed), Task 6 (deploy/Make); §6 deploy flow → Task 6 (+ runbook); §7 ES sizing → Task 3 (`-Xms1g -Xmx1g`, single-node). All covered.
- **Verification realism:** infra tasks verify via `docker build`, `docker compose config`, `caddy validate`, and a local no-TLS stack smoke; the seed is a real pytest integration test. TLS/DNS itself can only be verified on the provisioned box (documented in the runbook).
- **Type consistency:** `seed_platform_admin(session, *, email, full_name, password, role="superuser")` is defined and consumed identically in Task 5's test and script. Compose image tags (`sacco-api:staging`, `sacco-portal:staging`) are consistent across Tasks 3–4 and the Make targets.
- **Open items (from spec §9):** the real `<domain>` and initial admin email are provided at provisioning time via `STAGING_DOMAIN` and `make staging-seed-admin EMAIL=`; no code depends on hardcoded values.
