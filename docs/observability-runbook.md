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

All telemetry is scrubbed before egress to remove secrets and PII. There are **two distinct scrubbing paths**, each with its own keyset and redaction marker; both live in `app/core/observability/scrubbing.py`.

### Path 1 — structlog processor (`scrub_event_dict`)

Runs over structlog event dicts. Any key that **substring-matches** (case-insensitively) an entry in `SCRUB_KEYS` has its value replaced with the literal string **`[scrubbed]`**. The `event` message key is never touched.

`SCRUB_KEYS` (the exact, authoritative set):

```
password, token, secret, jwt_kek, hashed_password,
national_id_number, email, phone, first_name, last_name, dob,
actor_label,
member_number, account_number, card_number, passport, routing_number
```

`actor_label` carries a user email (e.g. `"user@example.com (impersonating)"`) and is scrubbed here even though it is retained in the structlog contextvars for the `AuditableMixin` audit trail.

### Path 2 — Logfire span/log scrubbing (`ScrubbingOptions`)

Runs over span/log attributes inside Logfire before egress. The effective keyset is **Logfire's built-in `DEFAULT_PATTERNS` ∪ our `SCRUB_EXTRA_PATTERNS`** — we ADD to the defaults, we never replace or disable them.

- **Logfire defaults** (always on): `password`, `passwd`, `auth`, `authorization`, `credential`, `private_key`, `api_key`, `session`, `cookie`, `social_security`, `credit_card`, `csrf`, `xsrf`, `jwt`, `ssn`, … (see `logfire/_internal/scrubbing.py`).
- **`SCRUB_EXTRA_PATTERNS`** (our additions, regex substrings matched against attribute key paths): `national_id`, `first_name`, `last_name`, `\bdob\b`, `actor_label`, `email`, `phone`, `member_number`, `account_number`, `card_number`, `passport`, `routing_number`.

When a key matches, Logfire replaces the value with **`[Scrubbed due to '<matched-substring>']`**. We pass **no callback** — a callback that returned a value would *un-redact* Logfire's own matches, so it is intentionally absent (the previous callback did exactly that and was removed in the final egress-hardening pass).

### URL / query-string caveat (SAFE_KEYS)

Logfire's scrubber has a `SAFE_KEYS` allow-list it **never** scrubs, including `http.url`, `http.target`, `http.route`, `url.full`, `url.path`, `url.query`, and `db.statement`. The FastAPI/ASGI instrumentation records the request URL (with query string) and the resolved endpoint arguments. Free-text operator endpoints (`GET /search?q=…`, `GET /platform/search?q=…`, list filters) accept operator-typed member PII, which would land in those never-scrubbed attributes.

Two SDK-supported hooks on `logfire.instrument_fastapi` close this in `app/core/observability/instrument.py`:

- **`server_request_hook` (`_strip_query_server_request_hook`)** — strips the `?…` query portion off `http.url` / `http.target` / `url.full` and blanks `url.query` on the live server span at request start, keeping the path only.
- **`request_attributes_mapper` (`_drop_request_arguments`)** — returns `None` so the resolved endpoint arguments (`fastapi.arguments.values` / `.errors`) are not recorded at all; those echo operator-typed query/path values (e.g. a search term) that Logfire's key-name scrubber cannot catch (the param key `q` matches no pattern). Consistent with the strict/metadata-only egress posture.

### Keys NOT scrubbed (intentionally retained to aid debugging)

- Monetary amounts (`amount`, `balance`, `principal`, `interest`, `penalty`) — not identifying without the scrubbed PII.
- Request/response bodies and headers — never captured (`capture_headers` / `record_send_receive` default `False`).
- SQL bind parameters — never captured (SQLAlchemy instrumentation runs with parameter capture off).

### Metadata Retention

Scrubbing is metadata-only: operation names, status codes, latencies, error types, route templates, and structured fields (except those matched above) are preserved. This provides observability without exfiltrating secrets or PII.

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

If a user email or phone number appears in a trace, add the offending key to the right path in `app/core/observability/scrubbing.py`:

- For a **span/log attribute** (Logfire path), add a regex substring to `SCRUB_EXTRA_PATTERNS`. It is combined with Logfire's defaults; the value will render as `[Scrubbed due to '…']`.
- For a **structlog field** (console/JSON logs), add the key to `SCRUB_KEYS`. The value will render as `[scrubbed]`.

If PII appears in a **URL / query string or a captured endpoint argument**, the fix is the `server_request_hook` / `request_attributes_mapper` in `app/core/observability/instrument.py`, not the keysets — those attributes are in Logfire's never-scrubbed `SAFE_KEYS` (see the URL/query-string caveat above). Re-deploy after any change; scrubbing applies to future traces only.

## References

- Pydantic Logfire docs: https://docs.pydantic.dev/latest/concepts/logfire/
- Observability spec: `docs/superpowers/specs/2026-08-01-observability-logfire-design.md`
- Instrumentation code: `app/core/observability/`
- Metrics catalogue: `docs/metrics-catalogue.md`
- Alert runbooks: `docs/alert-runbooks/`
- Committed dashboard definitions: `infra/observability/logfire/dashboards/`
- Committed alert definitions: `infra/observability/logfire/alerts/`
