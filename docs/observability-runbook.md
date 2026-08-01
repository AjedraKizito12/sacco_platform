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

This section is filled in by Phase 5 Increments 2 and 3.

- **Increment 2** (Business metrics & custom spans): Add custom spans via `app.core.observability.traces`, emit domain metrics via `app.core.observability.metrics`.
- **Increment 3** (Dashboards & alerting): Wire Logfire dashboards and SQL-based alerts via the Logfire UI.

For now, all telemetry is automatic (FastAPI spans, SQLAlchemy instrumentation, Celery tasks). Custom instrumentation is registered at app startup via `app/main.py` once increments 2–3 land.

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
- Observability spec: `docs/superpowers/specs/2026-08-01-observability-logfire.md`
- Instrumentation code: `app/core/observability/`
