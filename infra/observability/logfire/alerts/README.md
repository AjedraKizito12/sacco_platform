# Logfire alert definitions

This directory holds **committed, in-repo source-of-truth definitions** for
the email-only alerts this platform ships (Phase 5, observability). They are
plain JSON files describing SQL-based Logfire alerts, not a live export —
there is no live Logfire project wired to this repo yet, so there was
nothing to export.

**Alerts are email-only.** There is no Slack/Discord/Opsgenie channel in
v1 — that was an explicit user decision, not an oversight. `channel` is
`"email"` on every definition in this directory.

## How these get applied

1. At deploy time, once a real Logfire project exists with `LOGFIRE_TOKEN`
   configured for an environment (staging/production), an operator (or an
   agent with the Logfire MCP tools) creates an email notification channel
   (`channel_create_webhook`/organization settings — whatever Logfire's
   current email-channel primitive is at apply time) and then recreates
   each alert here via `alert_create` or the Logfire web UI, wiring it to
   that channel.
2. **Once applied, the live Logfire project is authoritative.** Threshold
   tuning, window tuning, and new alerts should happen there, driven by
   what actually fires (or fails to fire) once real traffic and telemetry
   exist.
3. To keep this repo in sync, periodically re-export the live alert
   definitions (`alert_get`/`alert_list` via the Logfire MCP) and update the
   corresponding file here, so the repo reflects what's actually running.
   This directory is a reproducibility snapshot / starting point, not a
   continuously enforced config-as-code source.

**No MCP calls were made and nothing was created in any live Logfire
project, and no email channel was created anywhere, as part of authoring
these files.** This is pure in-repo definition authoring, per the reshaped
Task 11 scope.

## JSON schema

Each file is a single alert definition:

```json
{
  "name": "Human-readable alert name",
  "severity": "critical | warning",
  "source": "metric | spans | unavailable",
  "query": "The Logfire SQL this alert should evaluate, or (when SQL would be verbose/dialect-specific) a precise prose description of the query — precise enough that anyone wiring this up in the Logfire UI/MCP knows exactly what to build",
  "threshold": "The condition that trips the alert, e.g. \"> 5%\" or \"> 0 (any increase)\"",
  "window": "The evaluation window, e.g. \"5m\", \"1h\", or \"n/a\" for point-in-time gauge checks",
  "channel": "email",
  "notes": "Caveats, known limitations, minimum-sample guards, or — for unavailable alerts — exactly what instrumentation is missing"
}
```

Field notes:

- `severity` follows the two-tier scheme this platform uses everywhere
  else (no "info" tier for alerts — anything worth an email is at least a
  warning).
- `source` mirrors the dashboards' convention:
  - `spans` — Logfire's auto-instrumented trace/span data (FastAPI
    instrumentation from Phase 5 Increment 1). No custom metric exists for
    these.
  - `metric` — one of the 14 custom `sacco_*` OTel instruments emitted by
    `app/core/observability/metrics.py` (Phase 5 Increments 2-3). See
    `docs/metrics-catalogue.md` for the full list.
  - `unavailable` — the alert is a placeholder. The signal it would need
    is not emitted by anything shipped in Phase 5 (or, for `/readyz`,
    can't be emitted by an in-process tool like Logfire at all). `notes`
    states exactly what instrumentation/tooling gap exists. These are kept
    in the directory (not deleted) so the gap is visible and tracked
    rather than silently dropped, and so no query is written that could
    either never fire or always fire as a false positive.
- `query` is deliberately prose-first rather than committing to exact
  Logfire SQL syntax in every case, for the same reason as the dashboards:
  the SQL dialect/functions are best finalized against the live schema
  (`query_schema_reference` via the Logfire MCP) at apply time.

## The alert catalogue

| File | Severity | Source | Signal |
|------|----------|--------|--------|
| `api-error-rate.json` | critical | spans | HTTP 5xx rate > 5% over 5m |
| `p99-latency.json` | critical | spans | HTTP p99 duration > 5s over 10m |
| `outbox-dead-letter-growth.json` | critical | metric | `sacco_outbox_dead_lettered_total` grew in the trailing hour |
| `backup-age.json` | critical | metric | `sacco_backup_age_seconds` > 36h |
| `reporting-beat-missed.json` | critical | metric | `sacco_report_last_run_timestamp` stale by > 2x a report type's schedule |
| `overdue-invoices-growth.json` | warning | metric | `sacco_invoices_outstanding{status="overdue"}` grew > 10% in 24h |
| `single-tenant-traffic-share.json` | warning | spans | one `tenant_schema` > 10% of tenant-scoped request volume |
| `readyz-503.json` | critical | **unavailable** | `/readyz` 503 sustained > 2m — needs an external uptime prober |
| `db-connection-pool-exhausted.json` | critical | **unavailable** | DB pool exhaustion — needs a pool gauge or a Postgres exporter |
| `beat-task-missed-general.json` | critical | **unavailable** | any non-reporting beat task missed schedule — needs a general heartbeat gauge |
| `approvals-pending-age.json` | warning | **unavailable** | oldest pending approval > 24h — needs a pending-age gauge, not a decision counter |

Seven of eleven alerts are backed by telemetry Phase 5 actually emits;
four are staged placeholders documenting exactly what future
instrumentation would be needed to make them real. See
`docs/metrics-catalogue.md` for the full metric catalogue and
`docs/alert-runbooks/` for the response runbook per alert.
