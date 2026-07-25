# Hetzner Staging — Deployment Guide Book

A complete, standalone walkthrough for standing up and operating the SACCO
platform **staging** environment on a single Hetzner VPS.

This is the long-form companion to the terse
[`hetzner-staging-runbook.md`](./hetzner-staging-runbook.md). If you already know
the environment and just need the commands, use the runbook. If you are
provisioning for the first time, debugging a deploy, or handing the box to
someone new, read this.

- **Design rationale:** `docs/superpowers/specs/2026-07-16-staging-deployment-design.md`
- **Implementation plan:** `docs/superpowers/plans/2026-07-17-staging-deployment.md`
- **Status:** Live since 2026-07-19 (PR #75). Merged to `main`.

> ⚠️ **This is staging, not production.** There are **no automated backups**
> (roadmap Phase 4), **no observability stack** (Phase 5), and **no rate
> limiting** (Phase 6). Application data lives only in Docker named volumes.
> **Losing the VPS loses the data.** Do not put anything irreplaceable here.

---

## 1. What you are deploying

The **entire application** runs on one Hetzner **CPX41** (≈8 vCPU / 16 GB RAM),
orchestrated by Docker Compose on a single internal bridge network
(`sacco_net`). **Only Caddy binds host ports** (80/443); every other service is
reachable only inside the Docker network — Postgres, Redis, RabbitMQ, and
Elasticsearch publish **no** host ports (unlike the local dev compose).

```
Internet
  │  :80 / :443  (TLS, auto Let's Encrypt via Caddy)
  ▼
┌─────────┐   staging.<domain>        ┌──────────┐
│  Caddy  │ ────────────────────────► │  portal  │  Next.js (node server.js, :3000, internal)
│ (proxy) │                           └────┬─────┘
│         │   api-staging.<domain>         │  server-side fetch → http://api:8000
│         │ ────────────────────────► ┌────▼─────┐
└─────────┘                           │   api    │  uvicorn (:8000, internal)
                                      └────┬─────┘
        worker ─┐   beat ─┐                │
                └─────────┴── share the api image ──┘
                                      │
   ┌───────────┬───────────┬──────────┴───┬─────────────────┐
 postgres    redis      rabbitmq     elasticsearch     (all internal-only, no host ports)
```

### The services (`docker-compose.staging.yml`)

| Service | Image / build | Role | Restart |
|---|---|---|---|
| **caddy** | `caddy:2` | Reverse proxy + auto-TLS; the only host-exposed service (80/443) | `unless-stopped` |
| **portal** | build `admin/apps/portal/Dockerfile` | Next.js production build (`node server.js`), port 3000 internal | `unless-stopped` |
| **api** | build `./Dockerfile` → `sacco-api:staging` | FastAPI (uvicorn), port 8000 internal | `unless-stopped` |
| **worker** | same `sacco-api:staging` image | Celery worker (`--concurrency=2`) | `unless-stopped` |
| **beat** | same `sacco-api:staging` image | Celery beat (periodic jobs) — single instance | `unless-stopped` |
| **migrate** | same `sacco-api:staging` image | One-shot `alembic upgrade head` | `"no"` |
| **postgres** | `postgres:16` | Primary datastore | `unless-stopped` |
| **redis** | `redis:7` | Cache, sessions, rate-limit counters | `unless-stopped` |
| **rabbitmq** | `rabbitmq:3.12-management` | Event bus / Celery broker | `unless-stopped` |
| **elasticsearch** | `elasticsearch:8.17.0` | Search index (heap capped at 1 GB) | `unless-stopped` |

The api image is **built once** (on the `api` service) and reused by `worker`,
`beat`, and `migrate` via the shared `sacco-api:staging` tag — so a deploy builds
the backend exactly once.

### Request & auth flow

- **Browser → Caddy → portal.** Portal server components and its `/api/auth/*`
  route handlers fetch the API **internally** at `http://api:8000`
  (`API_INTERNAL_URL`) — never over the public internet.
- **Browser → API direct** (TanStack Query mutations, the typed client) go to
  `https://api-staging.<domain>` with a **Bearer access token**. This is
  cross-origin, so the API must CORS-allow the portal origin (`ALLOWED_ORIGINS`)
  and the portal CSP `connect-src` must include the API origin
  (`NEXT_PUBLIC_API_BASE_URL`, baked at build time).
- **Refresh token** is an httpOnly Secure cookie set by the portal's own
  `/api/auth/*` handlers — **same-origin** to the portal subdomain, so no
  cross-site cookie is involved.

> **The single most common misconfiguration** is CORS/CSP drift: the API's
> `ALLOWED_ORIGINS` and the portal's `NEXT_PUBLIC_API_BASE_URL` must name the
> **same** `api-staging.<domain>`. `gen_staging_env.sh` sets both from one
> `STAGING_DOMAIN`, so if you use the script they stay in sync.

---

## 2. Prerequisites checklist

Before you touch the server, have:

- [ ] A **Hetzner Cloud account** and the ability to create a CPX41.
- [ ] A **domain** you control DNS for, and the ability to add two `A` records.
- [ ] An **SSH keypair** (the public key added to the Hetzner server at creation).
- [ ] An **email address** for Let's Encrypt expiry notices (`CADDY_ACME_EMAIL`).
- [ ] The **repo clone URL** (HTTPS or a deploy key for SSH).
- [ ] A chosen **initial superuser email** (e.g. `admin@<domain>`).

Two decisions to make up front:

| Decision | Where it's used |
|---|---|
| `<domain>` (e.g. `sacco.example`) | DNS records, `STAGING_DOMAIN`, Caddy, portal build |
| Initial superuser email | `make staging-seed-admin EMAIL=…` |

---

## 3. One-time VPS provisioning

Do this **once** per box. All of section 3 runs as **root** over SSH.

### 3.1 Create the VPS

1. Hetzner Cloud → create server → **CPX41** (8 vCPU / 16 GB), image **Ubuntu 24.04**.
2. Attach your SSH public key.
3. Note the server's **IPv4 address**.

### 3.2 Point DNS at the box

Add two `A` records at your DNS provider, both pointing at the VPS IPv4:

```
staging.<domain>       A   <VPS_IPv4>
api-staging.<domain>   A   <VPS_IPv4>
```

DNS must resolve **before** the first deploy — Caddy needs it to complete the
Let's Encrypt HTTP-01 challenge. Verify from your laptop:

```bash
dig +short staging.<domain>
dig +short api-staging.<domain>
# both must return <VPS_IPv4>
```

### 3.3 Create a hardened `deploy` user

Root SSH is for setup only; day-to-day runs as `deploy`.

```bash
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy   # copy authorized_keys
```

Then harden SSH in `/etc/ssh/sshd_config`:

```
PermitRootLogin no
PasswordAuthentication no
```

Reload and **verify you can still get in as `deploy` in a new session before
closing root**:

```bash
systemctl reload ssh
# In a SEPARATE terminal: ssh deploy@<VPS_IPv4>   ← must succeed
```

### 3.4 Firewall

Only SSH + HTTP + HTTPS are exposed. Everything else is internal to Docker.

```bash
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw --force enable
ufw status            # confirm 22/80/443 only
```

### 3.5 Install Docker Engine + Compose plugin

```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
```

Log out and back in as `deploy` so group membership takes effect, then confirm:

```bash
docker --version
docker compose version     # the plugin, not the legacy docker-compose
```

---

## 4. First deploy

From here on, run as the **`deploy`** user, from the repo root.

### 4.1 Clone the repo

```bash
git clone <repo-url> sacco-platform
cd sacco-platform
```

### 4.2 Generate secrets and the env file

`gen_staging_env.sh` copies `.env.staging.example` → `.env.staging`, mints strong
random secrets (`JWT_KEK`, `APP_SECRET_KEY`, `COOKIE_SECRET`, Postgres + RabbitMQ
passwords) with `openssl`, substitutes your domain everywhere, and `chmod 600`s
the result. It **refuses to overwrite** an existing `.env.staging`.

```bash
STAGING_DOMAIN=<domain> scripts/gen_staging_env.sh
```

Then open `.env.staging` and set the one value the script can't guess:

```bash
CADDY_ACME_EMAIL=you@<domain>
```

Skim the rest of the file. Key invariants (see §7 for the full reference):

- `APP_ENV=production` — this **enforces JWT auth** and forbids stub auth modes at boot.
- `ALLOWED_ORIGINS=["https://staging.<domain>"]` — a JSON array; keep the brackets.
- `NEXT_PUBLIC_API_BASE_URL=https://api-staging.<domain>` — must match the API origin.

> **Never commit `.env.staging`.** It is git-ignored. It holds every secret for
> the environment and is mode `600` (owner-read only).

### 4.3 Run the deploy

```bash
scripts/deploy.sh        # or: make deploy
```

`deploy.sh` performs, in order:

1. `git pull --ff-only` — fast-forward to latest `main`.
2. `docker compose … build` — build the api and portal images (first run is slow:
   Python deps + a full pnpm/Next production build; expect several minutes).
3. `docker compose … run --rm migrate` — `alembic upgrade head` as a **discrete
   step**, so a failed migration **aborts the deploy before** new app containers start.
4. `docker compose … up -d` — start/replace all long-running services.
5. `docker compose … ps` — print status.

### 4.4 Seed the login-capable superuser

The bootstrap platform user is created **without** a password and cannot log into
the portal. Seed a real superuser (idempotent by email; prompts for a password,
minimum 8 chars):

```bash
make staging-seed-admin EMAIL=admin@<domain>
```

To pre-supply the password non-interactively, export `SEED_ADMIN_PASSWORD` first.

### 4.5 Wait for TLS, then verify

Caddy obtains certificates lazily — the **first request** to each subdomain
triggers the ACME challenge. Hit both hosts once, then confirm:

```bash
# API readiness — all four dependencies must be "ok"
curl -s https://api-staging.<domain>/readyz | jq
# → {"status":"ok","checks":{"postgres":"ok","redis":"ok","rabbitmq":"ok","elasticsearch":"ok"}}

# API liveness (no dependency touch)
curl -s https://api-staging.<domain>/healthz
# → {"status":"ok"}
```

Then open **`https://staging.<domain>`** in a browser and log in with the seeded
admin. See §6 for the full acceptance checklist.

---

## 5. Ongoing deploys

Every subsequent code deploy is one command:

```bash
scripts/deploy.sh        # or: make deploy
```

Because `deploy.sh` sequences **build → migrate → up**, a broken migration stops
the deploy before it swaps in new app containers. The datastores keep their named
volumes across deploys, so no data is lost on a normal redeploy.

There is **no CI/CD** — deploys are manual `git pull` + compose on the server
(intentional; a pipeline is deferred). If you push to `main` and want it live,
SSH in and run the deploy.

---

## 6. Acceptance checklist (post-deploy smoke test)

Run through this after the first deploy and after any risky change:

- [ ] `https://staging.<domain>` serves the portal over **valid TLS** (no cert warning).
- [ ] `https://api-staging.<domain>/readyz` returns `200` with all four checks `ok`.
- [ ] You can **log in** as the seeded platform superuser.
- [ ] The portal **command palette / search** returns results (proves Elasticsearch
      + the `reconcile_search_indexes` beat are working — allow ~45s after first boot).
- [ ] `make staging-logs SVC=beat` shows periodic jobs firing (search reconcile,
      notification dispatch, billing, reporting, key rotation).
- [ ] `make staging-logs SVC=worker` shows the worker picking up tasks.
- [ ] Creating a tenant / exercising a flow persists across `make staging-down`
      + `make staging-up` (proves volumes are wired).

---

## 7. Configuration reference (`.env.staging`)

Generated from `.env.staging.example`. Grouped by concern:

### Domain & TLS
| Var | Meaning |
|---|---|
| `STAGING_DOMAIN` | Base domain; Caddy derives `staging.` and `api-staging.` hosts |
| `CADDY_ACME_EMAIL` | Let's Encrypt contact for expiry notices (**set manually**) |

### App
| Var | Value | Notes |
|---|---|---|
| `APP_ENV` | `production` | Flips the boot guard forbidding stub auth |
| `LOG_LEVEL` | `info` | |
| `STRUCTLOG_JSON` | `true` | JSON structured logs |
| `PLATFORM_AUTH_MODE` / `TENANT_AUTH_MODE` / `MEMBER_AUTH_MODE` | `jwt` | `stub` is rejected when `APP_ENV=production` |

### Secrets (auto-generated by `gen_staging_env.sh`)
| Var | Generation |
|---|---|
| `JWT_KEK` | base64 32 random bytes (KEK for signing keys) |
| `APP_SECRET_KEY` | hex 32 bytes |
| `COOKIE_SECRET` | hex 32 bytes |
| `POSTGRES_PASSWORD` | hex 24 bytes |
| `RABBITMQ_USER` / `RABBITMQ_PASSWORD` | `sacco` / hex 24 bytes |

### Datastore URLs (internal Docker hostnames)
| Var | Value |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://sacco:<pw>@postgres:5432/sacco` |
| `REDIS_URL` | `redis://redis:6379/0` |
| `RABBITMQ_URL` | `amqp://sacco:<pw>@rabbitmq:5672//` |
| `ELASTICSEARCH_URL` | `http://elasticsearch:9200` |

### CORS & portal wiring
| Var | Value | Notes |
|---|---|---|
| `ALLOWED_ORIGINS` | `["https://staging.<domain>"]` | JSON array (pydantic parses as JSON) — keep brackets |
| `NEXT_PUBLIC_API_BASE_URL` | `https://api-staging.<domain>` | Baked into the portal at build; browser bundle + CSP |
| `API_INTERNAL_URL` | `http://api:8000` | Runtime, server-side portal fetches |
| `REFRESH_COOKIE_NAME` | `sacco_refresh` | httpOnly refresh cookie name |

> Changing `NEXT_PUBLIC_API_BASE_URL` requires a **portal rebuild** (`deploy.sh`
> rebuilds), because it is compiled into the browser bundle and CSP.

---

## 8. Operations cookbook

All commands run as `deploy` from the repo root. Underlying compose invocation is
`docker compose -f docker-compose.staging.yml --env-file .env.staging`.

| Task | Command |
|---|---|
| Tail all logs | `make staging-logs` |
| Tail one service | `make staging-logs SVC=api` (or `worker`, `beat`, `portal`, `caddy`, `postgres`, …) |
| Service status | `docker compose -f docker-compose.staging.yml ps` |
| Stop the stack (keep data) | `make staging-down` |
| Start the stack | `make staging-up` |
| Rebuild images only | `make staging-build` |
| Full redeploy | `make deploy` |
| Reset a superuser password | `make staging-seed-admin EMAIL=<email>` |
| Shell into the api container | `docker compose -f docker-compose.staging.yml exec api bash` |
| Run a one-off migration check | `docker compose -f docker-compose.staging.yml run --rm migrate` |
| psql into Postgres | `docker compose -f docker-compose.staging.yml exec postgres psql -U sacco -d sacco` |

### Restarting a single service

```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging restart api
```

### Manual backup (until Phase 4 automates it)

There is **no automated backup**. For an ad-hoc snapshot of Postgres before a
risky change:

```bash
docker compose -f docker-compose.staging.yml exec -T postgres \
  pg_dump -U sacco -d sacco --format=custom > sacco-staging-$(date +%F).dump
# copy it OFF the box immediately — the box is not durable
scp deploy@<VPS_IPv4>:~/sacco-platform/sacco-staging-*.dump ./
```

Restore with `pg_restore` into a fresh database. **This is not a substitute for
Phase 4** — it's a manual safety net for one-off operations.

---

## 9. Troubleshooting

### TLS certificate won't issue / "connection not secure"
- **DNS not resolving yet.** `dig +short staging.<domain>` must return the VPS IP
  from the public internet. ACME HTTP-01 fails until it does.
- **Port 80 blocked.** ACME needs inbound `80`. Confirm `ufw status` allows it and
  Hetzner has no extra cloud firewall blocking it.
- Watch it happen: `make staging-logs SVC=caddy` — look for ACME order / challenge
  lines and any rate-limit errors from Let's Encrypt.

### `/readyz` returns `503` / `"degraded"`
The JSON `checks` object names the culprit (`postgres`/`redis`/`rabbitmq`/
`elasticsearch`). Tail that service's logs. Common causes:
- **Elasticsearch red / OOM.** ES heap is capped at 1 GB (`ES_JAVA_OPTS`). If ES is
  restarting, check `make staging-logs SVC=elasticsearch` and box memory (`free -h`).
- A datastore still starting — the api has healthcheck-gated `depends_on`, but a
  crash-looping store shows here.

### Portal loads but every API call fails (CORS error in browser console)
- `ALLOWED_ORIGINS` (API) and `NEXT_PUBLIC_API_BASE_URL` (portal) disagree. They
  must both name `https://api-staging.<domain>`. Fix `.env.staging`, then
  **rebuild the portal** (`make deploy`) since the value is baked at build time.

### Login fails for the seeded admin
- Re-run `make staging-seed-admin EMAIL=<email>` (idempotent; resets the password).
- Confirm `APP_ENV=production` and the three `*_AUTH_MODE=jwt` — a stub mode is
  rejected at boot in production and the api won't start.

### Deploy aborts on the migrate step
- Working as designed: a failed `alembic upgrade head` stops the deploy **before**
  new app containers start. Read the migrate output, fix the migration, redeploy.
  The previous app version keeps running.

### Build runs out of memory / is very slow
- On-box builds (Python deps + full pnpm/Next build) are the heaviest operation.
  The 16 GB box handles it, but if you've stacked other load, run the build when
  the box is quiet. Persistent strain is the signal to move to a registry-based
  deploy (deferred, Phase-later).

### Everything is down after a reboot
- All long-running services are `restart: unless-stopped` and come back on boot.
  If they don't, `make staging-up`. The one-shot `migrate` service does **not**
  auto-run on reboot (by design) — run `make deploy` if you need migrations.

---

## 10. Security notes

- **Only Caddy is internet-facing.** Postgres/Redis/RabbitMQ/ES have no host
  ports; they're reachable only inside `sacco_net`.
- **Secrets live in `.env.staging`** — git-ignored, mode `600`, owner-read only.
  No external secret manager (out of scope for staging).
- **SSH is key-only**, root login disabled, `deploy` is the operating user.
- **TLS** is automatic via Caddy + Let's Encrypt; certs persist in the
  `caddy_data` named volume across restarts.
- **RabbitMQ management UI** (port 15672) is **not** exposed to the host — reach it
  only via an SSH tunnel if you need it:
  `ssh -L 15672:localhost:15672 deploy@<VPS_IPv4>` after publishing the port
  temporarily, or `docker compose … exec rabbitmq rabbitmqctl …`.

---

## 11. What is deliberately NOT here (roadmap Phases 4–6)

| Missing capability | Roadmap phase | Consequence today |
|---|---|---|
| Automated backups / PITR | **Phase 4** | Data is in named volumes only; losing the box loses staging data |
| Observability / monitoring (LGTM) | **Phase 5** | No metrics/traces/dashboards; logs via `make staging-logs` only |
| Rate limiting / abuse protection | **Phase 6** | API is unthrottled |
| CI/CD pipeline | Deferred | Deploys are manual `git pull` + compose on the server |
| External secret manager | Deferred | Secrets are a server-only `.env.staging` |

None of these block staging use. They are production-launch gates — do not treat
this environment as production until they land.

---

## 12. File map

Everything that makes staging work:

| Path | Purpose |
|---|---|
| `docker-compose.staging.yml` | The staging stack (separate from dev `docker-compose.yml`) |
| `Caddyfile` | Reverse-proxy + auto-TLS config for both subdomains |
| `.env.staging.example` | Committed template; documents every variable |
| `.env.staging` | **Server-only, git-ignored** real secrets (generated) |
| `scripts/gen_staging_env.sh` | Generate `.env.staging` with strong random secrets |
| `scripts/deploy.sh` | Pull → build → migrate → up |
| `scripts/seed_platform_admin.py` | Idempotent first-login superuser seed |
| `admin/apps/portal/Dockerfile` | Multistage Next.js production (standalone) build |
| `Makefile` (`staging-*`, `deploy`) | Convenience targets over the compose invocation |
| `docs/deployment/hetzner-staging-runbook.md` | Terse quick-reference |
| `docs/deployment/hetzner-staging-guidebook.md` | This document |
