# Staging Deployment on Hetzner — Design

**Date:** 2026-07-16
**Status:** Approved (brainstorming) — pending spec review
**Goal:** Stand up a reproducible, HTTPS, full-stack **staging/testing** environment
for the SACCO platform on a single Hetzner VPS, deployable by `git pull` +
`docker compose`.

## 1. Scope

### In scope
- The **full application** on one Hetzner **CPX41** (≈8 vCPU / 16 GB):
  FastAPI API, Celery **worker** + **beat**, the Next.js **admin portal**
  (production build), and the backing stores (Postgres, Redis, RabbitMQ,
  Elasticsearch).
- A **Caddy** reverse proxy terminating TLS (auto Let's Encrypt) for two
  subdomains.
- Repo-side deliverables: a staging compose file, a production portal
  Dockerfile, a `Caddyfile`, an env template, deploy scripts / Make targets,
  a first-run superuser seed, and a provisioning runbook.

### Explicitly out of scope (deferred — roadmap Phases 4–6)
- Automated backups / PITR (Phase 4), observability/monitoring stack (Phase 5),
  rate limiting (Phase 6).
- CI/CD pipeline (image registry, GitHub Actions). Deploys are manual
  `git pull` + compose **on the server**.
- External secret manager. Secrets live in a server-only `.env.staging`.
- Data durability guarantees beyond Docker **named volumes**. Acceptable for
  staging; losing the box loses the data until Phase 4.

### Success criteria
- `https://staging.<domain>` serves the admin portal over valid TLS; an
  operator can log in as a seeded platform superuser and exercise the app.
- `https://api-staging.<domain>` serves the API (`/readyz` green: postgres,
  redis, rabbitmq, elasticsearch all `ok`).
- Celery **beat** periodic jobs run (search reconcile, notification dispatch,
  billing, reporting, key rotation) and the **worker** processes them.
- A code change → `deploy` → migrations applied → new version live, with no
  manual container surgery.

## 2. Architecture

Single VPS, everything in Docker Compose on one internal bridge network
(`sacco_net`). **Only Caddy binds host ports** (80/443); every other service is
reachable only inside the Docker network. Postgres/Redis/RabbitMQ/Elasticsearch
publish **no** host ports in staging (unlike the dev compose).

```
Internet
  │  :80/:443 (TLS, auto Let's Encrypt)
  ▼
┌─────────┐   staging.<domain>       ┌──────────┐
│  Caddy  │ ───────────────────────► │  portal  │ (next start, :3000, internal)
│ (proxy) │                          └────┬─────┘
│         │   api-staging.<domain>        │ server-side fetch → api:8000
│         │ ───────────────────────► ┌────▼─────┐
└─────────┘                          │   api    │ (uvicorn, :8000, internal)
                                     └────┬─────┘
        worker ─┐  beat ─┐                │
                └────────┴──── share the api image ───┘
                                     │
     ┌───────────┬───────────┬───────┴──────┬───────────────┐
  postgres     redis      rabbitmq     elasticsearch   (all internal-only)
```

### Auth / data flow (unchanged from the portal's existing design)
- **Browser → Caddy → portal.** Portal server components / route handlers fetch
  the API **internally** at `http://api:8000` (`API_INTERNAL_URL`).
- **Browser direct API calls** (TanStack Query mutations, typed client) go to
  `https://api-staging.<domain>` with a **Bearer access token** — cross-origin,
  so the API must CORS-allow the portal origin, and the portal CSP `connect-src`
  must include the API origin.
- **Refresh token** is an httpOnly Secure cookie set by the portal's own
  `/api/auth/*` route handlers — **same-origin** to the portal subdomain, so no
  cross-site cookie is involved.

## 3. Compose topology (`docker-compose.staging.yml`)

A **separate** staging compose file; the existing `docker-compose.yml` (local
dev) is left untouched.

| Service | Image / build | Command | Host ports | Notes |
|---|---|---|---|---|
| **caddy** | `caddy:2` + `Caddyfile` | — | **80, 443** | Auto-TLS; routes both subdomains; persists certs in a named volume |
| **api** | build `./Dockerfile` | default (uvicorn) | none | `depends_on` datastores healthy; migrations are sequenced by the deploy script (see §6), not via a compose `depends_on` |
| **worker** | **same api image** | `celery -A app.workers.celery_app worker --concurrency=2` | none | `restart: unless-stopped` |
| **beat** | **same api image** | `celery -A app.workers.celery_app beat` | none | single instance |
| **migrate** | **same api image** | `alembic upgrade head` | none | one-shot (`restart: "no"`), invoked explicitly by the deploy script via `run --rm` before `up -d` so a failed migration aborts the deploy |
| **portal** | build `admin/apps/portal/Dockerfile` | `node server.js` (standalone) | none | non-root; `NEXT_PUBLIC_API_BASE_URL` baked at build |
| **postgres** | `postgres:16` | — | none | strong password from env; named volume |
| **redis** | `redis:7` | — | none | named volume |
| **rabbitmq** | `rabbitmq:3.12` | — | none | strong creds; named volume |
| **elasticsearch** | ES 8 | — | none | single-node; **heap capped** `ES_JAVA_OPTS=-Xms1g -Xmx1g`; named volume |

To avoid duplicating the api image build three times, `worker`/`beat`/`migrate`
reference the same built image (build once on `api`, reuse via `image:` tag or
compose `extends`/anchors).

## 4. Configuration & secrets

- **`.env.staging.example`** — committed template with documented placeholders.
- **`.env.staging`** — generated **on the server**, git-ignored, never committed.
  Contains strong random values:
  - `JWT_KEK` — base64-encoded 32 random bytes.
  - `COOKIE_SECRET` — random (replaces the dev `dev-only-do-not-use...`).
  - `POSTGRES_PASSWORD`, RabbitMQ user/password.
  - `APP_ENV=production` — flips the boot guard that **forbids stub auth modes**;
    `PLATFORM_AUTH_MODE=jwt`, `TENANT_AUTH_MODE=jwt`, `MEMBER_AUTH_MODE=jwt`.
  - `ALLOWED_ORIGINS=https://staging.<domain>` (API CORS; already env-driven via
    `settings.allowed_origins`).
  - `DATABASE_URL`/`REDIS_URL`/`RABBITMQ_URL`/`ELASTICSEARCH_URL` → internal
    service hostnames.
- **Portal build args / env:**
  - `NEXT_PUBLIC_API_BASE_URL=https://api-staging.<domain>` (baked at build →
    browser bundle + CSP `connect-src`).
  - `API_INTERNAL_URL=http://api:8000` (runtime, server-side).
  - `REFRESH_COOKIE_NAME` / member variant as today; cookies `Secure` in prod.
- **Domain** is a single env var (e.g. `STAGING_DOMAIN`) consumed by the
  `Caddyfile` and the portal build.

## 5. Required code changes

All small; the portal changes live inside `admin/`.

1. **`admin/apps/portal/next.config.mjs` — configurable CSP.**
   Today `connect-src` is hardcoded to `http://localhost:8000/8001` (with a
   comment acknowledging the limitation). Change it to include
   `process.env.NEXT_PUBLIC_API_BASE_URL` (and `'self'`) at build time, and
   **drop `'unsafe-eval'`** when `NODE_ENV === 'production'`. Dev behavior
   unchanged when the env var is absent.

2. **`admin/apps/portal/Dockerfile` — new, multistage.**
   pnpm workspace install → `pnpm --filter @sacco/portal build` → copy Next
   **standalone** output (`.next/standalone`, `.next/static`, `public`) into a
   slim runtime stage, run as a non-root user with `node server.js`. Build args
   pass `NEXT_PUBLIC_API_BASE_URL`.

3. **Infra files (new, repo root / `docker/`):**
   `docker-compose.staging.yml`, `Caddyfile`, `.env.staging.example`.

4. **`Makefile` — staging/deploy targets** (`deploy`, `staging-up`,
   `staging-logs`, `staging-seed-admin`, …).

5. **First-run seed script** (`scripts/seed_platform_admin.py`): create an
   initial **platform superuser with a password** via `PlatformUserService`,
   reading email/password from env or an interactive prompt (NOT hardcoded).
   Needed because the bootstrap `platform_bootstrap_email` user is created
   **without** a password and cannot log into the portal.

> **Contract note (CLAUDE.md contract N):** the Phase 2 portal contract limits
> changes outside `admin/`. This deployment work legitimately adds
> infrastructure files at the repo root (compose, Caddyfile, deploy scripts,
> docs, a seed script) and Make targets. These are infra, not module code, and
> are sanctioned by the explicit deployment request. No `app/` business logic,
> alembic, or module boundaries are touched.

## 6. Deploy flow

### Provisioning runbook (documented in `docs/`, run once by the operator)
1. Create the CPX41 VPS; note its IPv4.
2. DNS: `A` records for `staging.<domain>` and `api-staging.<domain>` → VPS IP.
3. Create a non-root `deploy` user; harden SSH (key-only).
4. Install Docker Engine + compose plugin.
5. `ufw`: allow 22, 80, 443; deny the rest.
6. `git clone` the repo as `deploy`.
7. Generate `.env.staging` (helper script emits strong random secrets).
8. `make deploy` (first run builds everything).
9. `make staging-seed-admin` to create the login-capable superuser.

### Ongoing deploys
`scripts/deploy.sh` (or `make deploy`):
```
git pull
docker compose -f docker-compose.staging.yml build
docker compose -f docker-compose.staging.yml run --rm migrate   # alembic upgrade head
docker compose -f docker-compose.staging.yml up -d
```
`migrate` runs as a discrete step so a failed migration aborts the deploy before
new app containers start.

## 7. Elasticsearch sizing

ES is the memory hog. On the 16 GB box, cap the JVM heap
(`ES_JAVA_OPTS=-Xms1g -Xmx1g`), run single-node
(`discovery.type=single-node`), and disable security for the internal-only
network (`xpack.security.enabled=false`) as today. Leaves ample RAM for
Postgres, the JVM, Node, and on-box image builds.

## 8. Risks & mitigations

- **On-box image builds are heavy** (Python deps + full pnpm/Next build).
  Mitigated by the 16 GB box; if builds strain the box later, move to the
  registry-based deploy method (deferred).
- **Secrets on disk.** `.env.staging` is git-ignored and root/`deploy`-readable
  only. Acceptable for staging; a secret manager is out of scope.
- **No backups.** Named volumes only. Explicitly accepted for staging until
  Phase 4.
- **CORS/CSP drift.** The single source of truth for the API origin is
  `NEXT_PUBLIC_API_BASE_URL` (portal) and `ALLOWED_ORIGINS` (API). Both must name
  the same `api-staging.<domain>`; the runbook and env template make this
  explicit.

## 9. Open questions (fill at provisioning time)

- The actual `<domain>` / subdomain names.
- Initial superuser email for `staging-seed-admin`.
