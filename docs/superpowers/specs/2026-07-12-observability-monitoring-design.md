# Phase 5 — Observability & Monitoring (Design)

**Status:** Approved (brainstorming, 2026-07-12)
**Roadmap:** `docs/superpowers/plans/saas-launch-roadmap.md` §Phase 5
**Register:** cross-cutting infrastructure + a thin config surface. Not a bounded context.

## Goal

Give the platform structured logs, Prometheus metrics, and distributed-tracing
readiness before real customer money flows, with the whole telemetry pipeline
runnable and **verified end-to-end in local Docker Compose** against a
self-hosted LGTM stack (Loki, Grafana, Tempo, Prometheus). Today logs go to
stdout only, there are no metrics, and there is no tracing.

## Scope decomposition

Phase 5 is large (roadmap: ~3 weeks). It splits into two increments, each a
standalone spec→plan→implementation cycle:

- **Increment 1 — App instrumentation + local LGTM stack (this plan).**
  Structured JSON logging with secret scrubbing; Prometheus metrics + a
  `/metrics` endpoint; business-metric gauges via a Celery beat task →
  Pushgateway; OpenTelemetry tracing scaffold (no-op unless configured); the
  LGTM + Pushgateway + OTEL-Collector stack behind an opt-in compose profile.
- **Increment 2 — Dashboards + alerting (follow-up).** The 8 Grafana dashboard
  JSONs, Alertmanager + the alert catalogue, and one runbook per alert.

This document specifies both increments; the accompanying plan implements
Increment 1 only.

## Deployment strategy: local-complete via a compose profile

Following Phase 4's precedent, the full stack runs locally so instrumentation
is verified against real backends — but under an **opt-in `observability`
compose profile** so `docker compose up` stays lean. Developers who want the
stack run `docker compose --profile observability up`. Production is an
endpoint/credential swap (point the OTLP exporter and Prometheus remote-write
at the managed collectors); no code changes.

Stack choice is **self-hosted LGTM** (roadmap). Grafana Cloud / Datadog are
explicitly not pursued.

## Architecture (Increment 1)

```
                        ┌────────── OTLP ──────────┐
   ┌───────────┐  /metrics scrape    ┌────────────┐│
   │  FastAPI  │◀───────────────────│ Prometheus │▼
   │  app      │─── traces (OTLP) ─▶│            │  ┌──────────────┐
   │  + metrics│                    └─────┬──────┘  │ OTEL         │
   │  middleware                          │ scrape  │ Collector    │──▶ Tempo
   └───────────┘                          ▼         └──────┬───────┘
   ┌───────────┐  push (60s)      ┌────────────┐           │ traces
   │  Celery   │─────────────────▶│ Pushgateway│◀──────────┘
   │  beat:    │  business gauges └────────────┘
   │  emit_*   │
   └───────────┘        stdout JSON logs ──▶ (Increment 2: Promtail → Loki)
                                             ┌─────────┐
   Prometheus + Tempo + Loki ──────────────▶│ Grafana │
                                             └─────────┘
```

All new app code lives in `app/core/observability/` (cross-cutting, imports
nothing from `app/modules` or `app/platform_` except read-only queries for
business gauges, which go through existing services, not direct model reach-in
where avoidable).

### Component 1: Structured logging + secret scrubbing

- `app/core/observability/logging.py`: a `scrub_sensitive` structlog processor
  that recursively redacts a configured key set anywhere in the event dict
  (values → `"[REDACTED]"`). Default keys: `password`, `token`,
  `access_token`, `refresh_token`, `authorization`, `secret`, `jwt_kek`,
  `hashed_password`, `private_key`, `national_id_number`, `email`,
  `card_number`. Case-insensitive key match; substring match on a small set of
  suffixes (`_token`, `_secret`, `_password`) so derived keys are caught.
- Inserted into the existing processor chain in `app/main.py`'s
  `_configure_logging()` **before** the JSON/console renderer, after
  `merge_contextvars`. The current `structlog_json` toggle and `request_id`
  contextvar binding are unchanged.
- New setting `log_scrub_keys: list[str]` (defaults above), so ops can extend
  the set without code changes.
- The same processor chain is applied in the Celery worker bootstrap (workers
  currently inherit whatever `app.main` import side-effects give them; make the
  configuration explicit in `app/workers/celery_app.py`).

### Component 2: Prometheus metrics + `/metrics`

- Add `prometheus-client`.
- `app/core/observability/metrics.py`: owns a `CollectorRegistry` and the
  metric objects:
  - `sacco_http_requests_total{method, path, status}` (Counter)
  - `sacco_http_request_duration_seconds{method, path}` (Histogram)
  - `sacco_auth_login_attempts_total{outcome, actor_type}` (Counter)
  - business gauges (registered on a separate registry pushed from the worker,
    see below): `sacco_tenants_total{status}`, `sacco_subscriptions_total{status}`,
    `sacco_subscriptions_mrr{currency}`, `sacco_invoices_outstanding{status}`,
    `sacco_loans_total{status}`.
  - Path label uses the **route template** (`/platform/tenants/{tenant_id}`),
    never the raw path, to bound cardinality.
- An ASGI/HTTP middleware in `app/main.py` records count + duration per request
  using the matched route template. Guarded by `settings.metrics_enabled`.
- `GET /metrics` renders `generate_latest(registry)` with the Prometheus
  content type. Plain endpoint — NOT subscription-gated, NOT auth-gated
  (Prometheus scrapes it); documented as internal-network-only in production
  (never behind the public LB). Returns 404 when `metrics_enabled` is false.
- Business gauges: a new Celery beat task `emit_business_metrics_gauges` (60s)
  computes the gauge values (tenant counts by status, MRR from `active`/
  `trialing` subscriptions per the existing dashboard-stats convention,
  outstanding invoices, loan counts) and **pushes to a Pushgateway** (workers
  are separate processes and can't be scraped directly). `pushgateway_url`
  setting; the task no-ops when unset.

### Component 3: OpenTelemetry tracing scaffold

- Add `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, and the FastAPI /
  SQLAlchemy / Celery instrumentation packages.
- `app/core/observability/tracing.py`: `configure_tracing(app=None)` sets up a
  `TracerProvider` with an OTLP span exporter targeting
  `settings.otel_exporter_otlp_endpoint`; instruments FastAPI (if `app`
  passed), SQLAlchemy (the async engine), and Celery.
- **No-op when `otel_exporter_otlp_endpoint` is unset** — the default dev stack
  and the whole test suite run untouched. Called from the FastAPI lifespan and
  the celery app bootstrap, both guarded by the endpoint check.
- Trace context propagation reuses the existing `request_id` where practical
  (bind trace_id into structlog contextvars so logs and traces correlate).

### Component 4: Local LGTM stack (compose profile `observability`)

- `infra/observability/` holds the stack config:
  - `prometheus/prometheus.yml` — scrape the API `/metrics` and the Pushgateway.
  - `otel-collector/config.yaml` — receive OTLP, export spans to Tempo.
  - `grafana/provisioning/datasources/` — Prometheus, Tempo, Loki datasources.
  - `tempo/tempo.yaml`, `loki/loki-config.yaml` — minimal single-binary configs.
- `docker-compose.yml` gains services `prometheus`, `grafana`, `tempo`, `loki`,
  `pushgateway`, `otel-collector`, all tagged `profiles: ["observability"]` so
  they only start with `--profile observability`.
- Increment 1's bar: bring the stack up, hit some API routes, and confirm
  (a) Prometheus has `sacco_http_requests_total` samples, (b) Pushgateway shows
  the business gauges after a beat cycle, (c) Tempo has spans for a traced
  request. Dashboards that render these are Increment 2.

### Component 5: Config + dependencies

New settings on `app/core/config.py`:
- `metrics_enabled: bool = True`
- `otel_exporter_otlp_endpoint: str | None = None`
- `pushgateway_url: str | None = None`
- `log_scrub_keys: list[str] = [<defaults>]`

New dependencies (justified in the commit per the CLAUDE.md dependency rule;
all additive, no substitution of the fixed stack):
`prometheus-client`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp`,
`opentelemetry-instrumentation-fastapi`,
`opentelemetry-instrumentation-sqlalchemy`,
`opentelemetry-instrumentation-celery`. Pin exact versions (OTEL SDK pins drift
and break at runtime — roadmap risk).

## Increment 2 (specified, not planned here)

- **8 Grafana dashboards** (JSON, provisioned): platform overview, billing,
  maker-checker, outbox, reporting, background jobs, database, per-tenant
  drilldown.
- **Alertmanager** + the two-tier alert catalogue (critical → page, warning →
  Slack) from the roadmap, wired to Prometheus rules.
- **One runbook per alert** under `docs/alert-runbooks/`.
- **Loki log shipping** (Promtail or the collector's filelog receiver) so the
  JSON logs land in Loki and correlate with traces by `request_id`/`trace_id`.
- `docs/observability-runbook.md`, `docs/metrics-catalogue.md`.

## CLAUDE.md changes (Increment 1)

- Roadmap table row 5 → **In progress — increment 1**.
- New **Observability contracts** subsection: all observability code lives in
  `app/core/observability/`; the secret-scrubbing processor is mandatory in
  every logging config (app + workers); `/metrics` is unauthenticated and
  internal-only in prod; tracing is a no-op unless the OTLP endpoint is set;
  business gauges are pushed from the beat task, never scraped from workers;
  the LGTM stack is opt-in via the `observability` compose profile.
- Note the sanctioned scope exception (like Phase 4): edits `docker-compose.yml`,
  adds `infra/observability/`, `app/core/observability/`, worker + main wiring,
  and `pyproject.toml` deps.

## Out of scope (Increment 1)

- All of Increment 2 (dashboards, alerting, runbooks, Loki shipping).
- Datadog / Grafana Cloud alternatives.
- Per-endpoint SLO definitions.
- Log-based metrics / trace-based metrics (needs the collector pipelines from
  Increment 2).
- Sampling strategy tuning (default parent-based always-on locally; production
  sampling is an Increment 2 / launch-tuning concern).

## Testing strategy (Increment 1)

- **Unit:** the scrubber (nested dicts, list values, the full key set, the
  suffix-match keys, non-string values pass through); business-gauge value
  computation against a seeded DB.
- **Integration:** `/metrics` returns 200 with the Prometheus content type and
  contains `sacco_http_requests_total` after a request is made; `/metrics`
  returns 404 when `metrics_enabled=false`; tracing config is a no-op (no
  exporter created) when the OTLP endpoint is unset.
- **Infra (the real proof):** `docker compose --profile observability up`,
  drive a few API routes + wait one beat cycle, then assert Prometheus has HTTP
  samples, Pushgateway has the business gauges, and Tempo has spans. Capture as
  a short verification note.
- Offline `alembic upgrade --sql` is broken repo-wide — but this increment adds
  **no migration** (no new tables), so that caveat doesn't apply here.

## Open decisions (resolved)

- Scope → **decompose**; Increment 1 (instrumentation + stack) now, Increment 2
  (dashboards + alerting) later.
- Local stack → **local-complete via an opt-in `observability` compose profile**.
- Hosting → **self-hosted LGTM** (production = endpoint swap).
- Worker metrics → **Pushgateway** (workers can't be scraped).
- Tracing default → **off** (no-op) unless the OTLP endpoint env var is set.
