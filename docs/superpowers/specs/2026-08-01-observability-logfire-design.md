# Phase 5 — Observability & Monitoring (Logfire) — Design

**Status:** Approved (brainstorming, 2026-08-01)
**Roadmap:** `docs/superpowers/plans/saas-launch-roadmap.md` §Phase 5
**Supersedes:** `docs/superpowers/specs/2026-07-12-observability-monitoring-design.md`
(the self-hosted LGTM design — never implemented; replaced by the Logfire
decision below).
**Register:** cross-cutting infrastructure + a thin config surface. Not a
bounded context.

## Goal

Give the platform structured logs, distributed traces, and business metrics
before real customer money flows, so problems surface on a dashboard instead of
a customer phone call. Today logs go to stdout only, there are no metrics, and
there is no tracing.

## Key decisions (settled in brainstorming)

1. **Backend: Pydantic Logfire** — hosted, OpenTelemetry-native, with
   first-class auto-instrumentation for FastAPI, SQLAlchemy/asyncpg, Celery,
   Redis, and HTTPX. Chosen over self-hosted LGTM and a backend-agnostic OTel
   layer because it matches the existing Pydantic/FastAPI/SQLAlchemy stack, the
   Logfire MCP is already available in this environment, and it removes an
   entire self-hosted-stack operational burden. Tradeoff accepted: per-span
   hosted billing and data egress to a SaaS (mitigated by the strict egress
   posture below).
2. **Scope: full Phase 5, three increments** in one spec (foundation →
   business metrics → dashboards/alerts/runbooks). The plan implements them in
   order with review checkpoints.
3. **Egress posture: strict / metadata-only.** Traces carry trace shape, span
   names, durations, status codes, `tenant_schema`, `actor_type`, entity ids,
   and SQL statement *shape* only. Bind parameters, request/response bodies,
   secrets, and member PII are scrubbed before anything leaves the process.

## What changes vs. the roadmap

The roadmap §Phase 5 assumed self-hosted LGTM. Under Logfire:

- **Removed:** `infra/observability/` LGTM `docker-compose.yml`, Prometheus
  rules, Alertmanager YAML, Grafana dashboard JSONs, Pushgateway, OTEL
  Collector. None of these are built.
- **Removed:** the `GET /metrics` Prometheus scrape endpoint. Logfire is the
  single metrics sink (via OTel metrics over OTLP); a parallel Prometheus path
  is not maintained.
- **Kept:** the `/readyz` enhancement (per-dependency latency), the
  business-metric gauge task, the metric catalogue (as Logfire metrics), and
  the alert catalogue (as Logfire SQL alerts).
- **Dashboards & alerts** live in Logfire (managed via the Logfire MCP),
  not in the admin portal.

## Architecture & module layout

A focused library under `app/core/observability/` plus configuration. No new
bounded context, no database changes.

```
app/core/observability/
  __init__.py        public surface: configure_observability(), context helpers
  config.py          env/token resolution, send_to_logfire gating, environment/service tags
  logging.py         structlog <-> Logfire bridge (existing structlog config is kept)
  scrubbing.py       the scrub keyset + callback (SINGLE SOURCE OF TRUTH)
  instrument.py      auto-instrument FastAPI, SQLAlchemy/asyncpg, Celery, Redis, HTTPX
  context.py         bind tenant_schema / actor_type / actor_id / impersonation_id onto spans
  metrics.py         (Increment 2) business metric instruments
```

Files touched outside the library: `app/main.py` (call
`configure_observability()` at startup; enhance `/readyz`),
`app/workers/celery_app.py` (worker/beat init + `emit_business_metrics_gauges`
beat entry), `pyproject.toml` (add `logfire` extras), `docker-compose.yml` /
`docker-compose.staging.yml` (env only — `LOGFIRE_TOKEN`,
`LOGFIRE_ENVIRONMENT`), `docs/`, `CLAUDE.md`.

**Explicitly not touched:** `admin/` (no portal changes — respects contract N),
`alembic/` (no migrations), any financial or business-logic code path (spans
and counters wrap existing calls; they never change behaviour).

## Configuration & egress gating

`configure_observability()` is the ONLY place Logfire is configured. It resolves:

- **Token:** `LOGFIRE_TOKEN` (write token; from secrets in staging/prod).
- **`send_to_logfire` gating:**
  - Token present -> `send_to_logfire=True` (staging/prod).
  - Token absent, `APP_ENV != production` -> `send_to_logfire=False`,
    spans/logs render to console (local dev).
  - **Tests -> always `send_to_logfire=False`** regardless of token (mirrors the
    NullProvider discipline from notifications). No telemetry leaves in CI.
- **Tags:** `environment` (dev/staging/prod from `APP_ENV`) and `service`
  (`api` / `worker` / `beat`) on every span.

`configure_observability()` is idempotent and safe to call from both the API
lifespan and the Celery worker init.

## Scrubbing (the enforcement point)

A single scrub keyset lives in `scrubbing.py` and is applied in two places so
both span attributes and log records are covered:

- Logfire's `scrubbing` callback (span attributes, SQL, HTTP metadata).
- A structlog processor in `logging.py` (log event dicts).

Keyset (case-insensitive, substring match where the SDK supports it):
`password`, `token`, `secret`, `jwt_kek`, `hashed_password`,
`national_id_number`, `email`, `phone`, `first_name`, `last_name`, `dob`.
Plus Logfire's built-in default patterns.

**Monetary amounts are intentionally NOT scrubbed** — they aid debugging and
are not personally identifying on their own. Amounts appear in spans and log
records; PII that would tie an amount to a person (names, ids, contact fields)
is scrubbed, so a leaked amount is not attributable.

Additional hard settings for the strict posture:
- SQLAlchemy/asyncpg **bind-parameter capture disabled** (statement shape only).
- FastAPI request/response **body capture disabled**.
- Redis command-argument capture disabled where it may carry keys/values.

An Increment-1 test asserts a known secret value and a known PII value never
appear in the emitted span/log payload (using a local capture exporter with
`send_to_logfire=False`).

## Tenant & actor context on spans

`context.py` reads the existing structlog contextvars already bound by the
request/worker middleware — `request_id`, `tenant_schema` (from search-path
resolution), `actor_type`, `actor_id`, and `impersonation_id` (bound by the
tenant auth deps per the impersonation contracts) — and attaches them as span
attributes. This is what makes per-tenant trace filtering and
impersonation-aware auditing possible in Logfire. It binds ids/labels only,
never PII, consistent with what already lands in `audit_log`.

## Increments

### Increment 1 — Foundation

Instrumentation, scrubbing, context, config. Load-bearing; everything else
depends on it.

- `configure_observability()` wired into `app/main.py` and
  `app/workers/celery_app.py`.
- Auto-instrument FastAPI, SQLAlchemy/asyncpg, Celery, Redis, HTTPX.
- Scrubbing keyset + callback + structlog processor; bind-param/body capture
  disabled.
- Tenant/actor span context helper.
- `/readyz` per-dependency latency.
- **Proof:** run the stack, hit an endpoint, confirm a trace with tenant
  context and scrubbed params lands in Logfire (or console in dev). Scrubbing
  test green.

### Increment 2 — Business metrics & custom spans

- `emit_business_metrics_gauges` Celery beat task (every 60s) recording OTel
  gauges: `sacco_tenants_total{status}`, `sacco_subscriptions_total{status}`,
  `sacco_subscriptions_mrr{currency}` (**active + trialing only**, matching the
  existing dashboard-stats MRR contract), `sacco_invoices_outstanding{status}`,
  `sacco_loans_total{status}`, `sacco_outbox_queue_depth{schema}`,
  `sacco_backup_age_seconds` (from Phase 4 `platform.backup_runs`).
- Custom spans / counters on key flows (thin wrappers, no logic change):
  maker-checker decisions (pending age, self-reject attempts), outbox publish
  latency + dead-letter counter, report materialization duration + last-run
  timestamp, auth login attempts `{outcome,actor_type}`.
- Metric labels are statuses/ids/currencies only — never PII.

### Increment 3 — Dashboards, alerts, runbooks

- **Dashboards** (via Logfire MCP): Platform overview, Billing, Maker-checker,
  Outbox, Reporting, Background jobs, Database, Tenant drilldown. Exported to
  `infra/observability/logfire/dashboards/` as JSON where the Logfire API
  supports export, for reproducibility.
- **Alerts** (via Logfire MCP, SQL-based):
  - *Critical (page):* API error rate >5% over 5min; p99 latency >5s sustained
    10min; outbox dead-letter count grew this hour; any beat task missed 2x its
    schedule; `/readyz` 503 >2min; backup age >36h.
  - *Warning:* approvals pending >24h; overdue invoices +10% in 24h; any
    single tenant >10% of total requests.
  - Channel: **email only** for v1 (both tiers). A Slack webhook channel is a
    trivial add-on when a workspace is available — deferred, not designed out.
- **Docs:** `docs/observability-runbook.md` (scrub policy, token/env setup, how
  to add a metric/dashboard/alert), `docs/metrics-catalogue.md`,
  `docs/alert-runbooks/` (one MD per alert with response steps).
- **CLAUDE.md close-out:** roadmap row 5 -> Done; new "Observability contracts"
  section; Phase 5 scope note under contract N.

## Contracts to establish (into CLAUDE.md at close-out)

- `configure_observability()` (`app/core/observability/`) is the ONLY place
  Logfire is configured. Do not call `logfire.configure()` elsewhere.
- The scrub keyset in `scrubbing.py` is the single source of truth. Adding a
  field that could carry PII or a secret means adding it to the keyset.
- No code sends member PII or secrets to spans, logs, or metrics. SQL bind
  params, request/response bodies, and the scrub keyset stay disabled/scrubbed.
- `send_to_logfire` is token-gated and **always off in tests**.
- Metric label sets are statuses/ids/currencies only. Metric names are prefixed
  `sacco_`.
- Business-metric gauges are emitted only by `emit_business_metrics_gauges`;
  MRR counts `active` + `trialing` subscriptions only (aligns with the
  dashboard-stats MRR contract).

## Dependencies

- Add `logfire` with `[fastapi,sqlalchemy,celery,redis,httpx]` extras to
  `pyproject.toml` (justified in the commit per the no-undocumented-deps rule).
- Soft prerequisite satisfied: Phase 4 `backup_runs` already exists and feeds
  `sacco_backup_age_seconds`.
- Downstream: Phase 6 (rate limiting) consumes these metrics; production launch
  gates on this phase.

## Non-goals

- No self-hosted LGTM stack (Loki/Grafana/Tempo/Prometheus/Mimir/Alertmanager).
- No Prometheus `GET /metrics` scrape endpoint.
- No admin-portal changes; dashboards live in Logfire.
- No Next.js portal APM (roadmap's "portal request logs to same stack" is
  deferred to a follow-up once the API side is proven).
- No database changes.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A PII field escapes the scrub keyset | Medium | High | Strict posture (bodies/bind-params off by default); scrubbing test; staging trace review before prod |
| Logfire span bill grows under load | Medium | Medium | Sampling configurable via SDK; review volume after staging soak |
| SDK/instrumentation pin drifts and breaks at runtime | Low | Medium | Pin `logfire` version; verify in staging before prod |
| Alert fatigue from aggressive thresholds | Medium | Medium | Start conservative; tune during Increment 3 |

## Effort

Reduced from the roadmap's L (3 wk, self-hosted LGTM) to **S–M** — the SDK's
auto-instrumentation removes the collector/exporter/dashboard-plumbing work.
Increment 1 is the bulk of the engineering; Increments 2–3 are mostly
configuration, metric definitions, and dashboard/alert authoring via the MCP.
