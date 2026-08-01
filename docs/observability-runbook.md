# Observability Runbook

## Overview

**Logfire** is a hosted OpenTelemetry backend (Pydantic) providing a unified sink for metrics, traces, and logs across the SACCO platform. Phase 5 Observability integrates it as the single observability platform for staging and production deployments.

Logfire is **optional** in development and test environments; configure the token to enable egress, or leave it unset to log to the console only.

## Configuration & Egress Control

Telemetry egress to Logfire is controlled by the `send_to_logfire` setting in `app.settings`:

| Condition | Behavior |
|-----------|----------|
| `LOGFIRE_TOKEN` set + `APP_ENV ≠ test` | Egress enabled (all traces, spans, logs sent to Logfire) |
| `LOGFIRE_TOKEN` unset + `APP_ENV = development` | Console only (structured JSON logs to stdout, no egress) |
| `LOGFIRE_TOKEN` unset + `APP_ENV = staging/production` | Console only (logs to stdout; **data loss** — use a token in production) |
| `APP_ENV = test` OR any pytest run | Always OFF (no egress, even if token is set; avoids test telemetry pollution) |

## Data Scrubbing Policy

All telemetry is scrubbed before egress to remove secrets and PII. The **authoritative scrub keyset** lives in `app/core/observability/scrubbing.py` (`SCRUB_KEYS` constant).

### Scrubbing Rules

- **Keys always scrubbed** (value replaced with `***SCRUBBED***`):
  - Authentication: `password`, `token`, `jwt`, `refresh_token`, `access_token`, `authorization`, `api_key`, `secret`
  - User identity: `email`, `phone`, `actor_label` (carries user email in audit trails)
  - Sensitive profile: `national_id_number`, `passport_number`, `phone_number`
  - Financial: `account_number`, `card_number`, `routing_number`

- **Keys NOT scrubbed** (intentionally retained to aid debugging):
  - Monetary amounts (`amount`, `balance`, `principal`, `interest`, `penalty`) — these are not identifying without the scrubbed PII
  - Request/response bodies — binary; capture headers only, never body content
  - SQL bind parameters — never captured (SQLAlchemy instrumentation is off by default)

### Metadata Retention

Scrubbing is metadata-only: operation names, status codes, latencies, error types, and structured fields (except those in `SCRUB_KEYS`) are preserved. This provides observability without exfiltrating secrets or PII.

## Per-Environment Setup

### Local Development

```bash
# Option 1: Console logging only (default)
# Unset LOGFIRE_TOKEN or set to empty string.
unset LOGFIRE_TOKEN
docker compose up -d api

# Option 2: Send to Logfire (if you have a token)
export LOGFIRE_TOKEN=<your-write-token>
docker compose up -d api
```

**Local logs** are structured JSON on stdout (via `STRUCTLOG_JSON=false` in `.env`); no file storage.

### Staging Deployment

1. Obtain a Logfire write token from the Pydantic console.
2. Add to `.env.staging` (git-ignored):
   ```bash
   LOGFIRE_TOKEN=<write-token>
   ```
3. Deploy:
   ```bash
   docker compose -f docker-compose.staging.yml up -d
   ```

**Staging env** sets `APP_ENV=production`, so `send_to_logfire` is enabled only if `LOGFIRE_TOKEN` is set.

### Production Deployment

**Production MUST have a `LOGFIRE_TOKEN` set** in the secure environment variables or `.env.production`. Without it, logs write to stdout only; monitoring and alerting will be blind.

```bash
export LOGFIRE_TOKEN=<write-token>
# Deploy via your production orchestration (Kubernetes, systemd, etc.)
docker run -e LOGFIRE_TOKEN=$LOGFIRE_TOKEN -e APP_ENV=production ...
```

## How to Add a Metric / Dashboard / Alert

### Adding a metric

1. Declare a new gauge/counter/histogram handle in
   `app/core/observability/metrics.py` via `logfire.metric_gauge` /
   `logfire.metric_counter` / `logfire.metric_histogram`, following the
   `sacco_`-prefixed naming convention. Choose labels carefully — labels
   are statuses/ids/currencies/report_type/schema only, **never PII**.
2. Call `.set()` / `.add()` / `.record()` at the appropriate call site (a
   beat task for a gauge like the business metrics, or inline at a flow
   point for a counter/histogram like the outbox/maker-checker/reporting/
   auth instrumentation).
3. Add the new metric's name, type, labels, and source to
   `docs/metrics-catalogue.md` — that document is the single
   human-readable index of every `sacco_*` metric and must stay in sync
   with `metrics.py`.
4. If the metric backs a dashboard panel or an alert, add/update the
   relevant JSON file(s) under `infra/observability/logfire/` (see below).

### Adding a dashboard

Dashboard definitions are committed JSON under
`infra/observability/logfire/dashboards/` (schema and authoring
conventions documented in that directory's own `README.md`). Add a new
`<name>.json` file there, following the existing `{title, description,
panels[]}` shape, then apply it to the live Logfire project via the
Logfire MCP (`dashboard_create` + `dashboard_add_panel`) or the web UI at
deploy time.

### Adding an alert

Alert definitions are committed JSON under
`infra/observability/logfire/alerts/` (schema and authoring conventions
documented in that directory's own `README.md`). Alerts are **email-only**
— there is no Slack/Discord/Opsgenie channel in v1. Add a new `<name>.json`
file there following the existing `{name, severity, source, query,
threshold, window, channel, notes}` shape, add a matching runbook under
`docs/alert-runbooks/<name>.md` (trigger condition, likely causes,
response steps, escalation), and cross-check every metric name the alert
references against `docs/metrics-catalogue.md` / `metrics.py` before
committing. If the alert needs a signal Phase 5 doesn't emit, mark
`"source": "unavailable"` with a `notes` field stating exactly what
instrumentation is missing — never write a query that can never fire or
would always false-positive.

### Applying committed definitions to a live Logfire project

Dashboards and alerts in this repo are **source-of-truth definitions, not
a live export** — authored before any real Logfire project existed for
this platform. At deploy time (staging or production, once
`LOGFIRE_TOKEN` is configured for that environment):

1. An operator (or an agent with the Logfire MCP tools) reads each JSON
   file under `infra/observability/logfire/dashboards/` and
   `infra/observability/logfire/alerts/` and recreates the equivalent
   dashboard/alert in the live project, via the Logfire MCP
   (`dashboard_create`/`dashboard_add_panel`, `alert_create`) or the
   Logfire web UI.
2. For alerts, create the email notification channel first and wire every
   alert to it — email is the only channel in v1.
3. Once applied, **the live Logfire project becomes authoritative** for
   day-to-day tuning (thresholds, panel layout, new variables). Periodically
   re-export (`dashboard_get`/`alert_get`) and overwrite the corresponding
   file here so the repo reflects what's actually running — this directory
   is a reproducibility snapshot, not a continuously enforced
   config-as-code source (Logfire has no "apply this JSON" import API at
   time of writing).

See `docs/metrics-catalogue.md` for every `sacco_*` metric (type, labels,
source) and `docs/alert-runbooks/` for the per-alert response runbook,
including the four staged/not-yet-backed alerts.

## Troubleshooting

### Egress Not Working

Check:
1. `LOGFIRE_TOKEN` is set and non-empty: `echo $LOGFIRE_TOKEN`
2. `APP_ENV` is not `test` (test always disables egress)
3. Network connectivity to Logfire (check container logs: `docker logs <api-container>`)

### Logs Missing from Logfire

- Verify `LOGFIRE_TOKEN` is a **write** token (not read-only).
- Check that scrubbing didn't mask fields you need (review `SCRUB_KEYS` in `app/core/observability/scrubbing.py`).
- If `APP_ENV=test` or running pytest, egress is intentionally disabled.

### PII Leaked in Traces

If a user email or phone number appears in a trace, add its JSON key to `SCRUB_KEYS` in `app/core/observability/scrubbing.py` and re-deploy. All future traces will scrub that key.

## References

- Pydantic Logfire docs: https://docs.pydantic.dev/latest/concepts/logfire/
- Observability spec: `docs/superpowers/specs/2026-08-01-observability-logfire-design.md`
- Instrumentation code: `app/core/observability/`
- Metrics catalogue: `docs/metrics-catalogue.md`
- Alert runbooks: `docs/alert-runbooks/`
- Committed dashboard definitions: `infra/observability/logfire/dashboards/`
- Committed alert definitions: `infra/observability/logfire/alerts/`
