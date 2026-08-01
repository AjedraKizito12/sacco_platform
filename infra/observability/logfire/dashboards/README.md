# Logfire dashboard definitions

This directory holds **committed, in-repo source-of-truth definitions** for
the eight Logfire dashboards this platform ships (Phase 5, observability).
They are plain JSON files, not Perses exports — there is no live Logfire
project wired to this repo yet, so there was nothing to export.

## How these get applied

1. At deploy time, once a real Logfire project exists with `LOGFIRE_TOKEN`
   configured for an environment (staging/production), an operator (or an
   agent with the Logfire MCP tools) reads each JSON file here and recreates
   the equivalent dashboard/panels in that Logfire project — via the Logfire
   MCP (`dashboard_create` + `dashboard_add_panel`) or the Logfire web UI.
2. **Once applied, the live Logfire project is authoritative.** Panel
   tweaks, new variables, layout changes, and alert wiring should happen
   there, driven by what operators actually find useful once real traffic
   and telemetry exist.
3. To keep this repo in sync, periodically re-export the live dashboard
   (`dashboard_get` via the Logfire MCP) and overwrite the corresponding
   file here, so the repo reflects what's actually running. This directory
   is a reproducibility snapshot / starting point, not a continuously
   enforced config-as-code source (Logfire has no "apply this JSON" import
   API at time of writing).

**No MCP calls were made and nothing was created in any live Logfire
project as part of authoring these files.** This is pure in-repo
definition authoring, per the reshaped Task 10 scope.

## JSON schema

Each file is a single dashboard definition:

```json
{
  "title": "Human-readable dashboard title",
  "description": "One or two sentences on what this dashboard is for and who uses it",
  "panels": [
    {
      "title": "Panel title",
      "type": "timeseries | stat | table | histogram",
      "source": "spans | metric | unavailable",
      "query": "The Logfire SQL this panel should run, or (when SQL would be verbose/dialect-specific) a precise prose description of the query over the named source — precise enough that anyone building the panel in the Logfire UI/MCP knows exactly what to wire up",
      "notes": "optional — caveats, known limitations, or exporter requirements"
    }
  ]
}
```

Field notes:

- `type` is the panel visualization: a time-bucketed line/area chart
  (`timeseries`), a single current-value tile (`stat`), a row-oriented
  list/drilldown (`table`), or a percentile/distribution view
  (`histogram`).
- `source` says where the data comes from:
  - `spans` — Logfire's auto-instrumented trace/span data (FastAPI, Celery,
    SQLAlchemy instrumentation from Phase 5 Increment 1). No custom metric
    exists for these; the panel queries span attributes/duration directly.
  - `metric` — one of the 14 custom `sacco_*` OTel instruments emitted by
    `app/core/observability/metrics.py` (Phase 5 Increments 2-3).
  - `unavailable` — the panel is a placeholder. The signal it would show is
    not emitted by anything shipped in Phase 5. `notes` explains what
    additional exporter/instrumentation would be required. These panels are
    intentionally kept in the JSON (not deleted) so the gap is visible and
    tracked, rather than silently dropped.
- `query` is deliberately prose-first rather than committing to exact
  Logfire SQL syntax in every case, since the SQL dialect/functions
  (`approx_percentile_cont`, `histogram_quantile`, JSON attribute access,
  etc.) are best finalized against the live schema
  (`query_schema_reference` via the Logfire MCP) at apply time, not guessed
  here against a project that doesn't exist yet. Where the query is a
  direct metric read, the description is precise enough to be typed in
  directly.

## Data availability

**None of these dashboards render real data in this development
environment.** Panels populate only once a deployed environment (staging
or production) runs with `LOGFIRE_TOKEN` set and Logfire instrumentation
actively shipping telemetry (the FastAPI/Celery/SQLAlchemy auto-instrumentation
from Increment 1, plus the `sacco_*` custom gauges/counters/histograms from
Increments 2-3). Local dev intentionally ships no telemetry.

## The eight dashboards

| File | Covers |
|------|--------|
| `platform-overview.json` | Golden signals (request rate, 5xx %, latency percentiles) from auto-instrumented FastAPI spans, plus `sacco_tenants_total` and a login-based active-session proxy. |
| `billing.json` | `sacco_subscriptions_total`, `sacco_subscriptions_mrr`, `sacco_invoices_outstanding`. |
| `maker-checker.json` | `sacco_maker_checker_decisions_total`, `sacco_maker_checker_self_reject_total`, plus a span-based drilldown table. |
| `outbox.json` | `sacco_outbox_queue_depth`, `sacco_outbox_dead_lettered_total`, `sacco_outbox_publish_duration_seconds`. |
| `reporting.json` | `sacco_report_materialize_duration_seconds`, `sacco_report_last_run_timestamp`. |
| `background-jobs.json` | Celery task spans (run rate, success/failure, p95 duration) — no custom metric backs this dashboard. |
| `database.json` | SQLAlchemy query spans for slow-query/top-statement/error-rate panels. Connection count, `pg_stat_statements` top-10, and replication lag are marked `"source": "unavailable"` — Phase 5 ships no server-side Postgres exporter. |
| `tenant-drilldown.json` | HTTP spans filtered by the `tenant_schema` span attribute (set via `bind_actor_context`), plus `sacco_outbox_queue_depth{schema=...}` (genuinely per-tenant) and `sacco_loans_total` / `sacco_tenants_total` (noted as platform-wide aggregates, not per-tenant sliceable, due to how those gauges are accumulated). |

## Metric name cross-check

Every `sacco_*` name referenced above was verified against the gauge/counter/
histogram handles declared in `app/core/observability/metrics.py`:

`sacco_tenants_total`, `sacco_subscriptions_total`, `sacco_subscriptions_mrr`,
`sacco_invoices_outstanding`, `sacco_backup_age_seconds`,
`sacco_outbox_queue_depth`, `sacco_loans_total`,
`sacco_auth_login_attempts_total`, `sacco_outbox_publish_duration_seconds`,
`sacco_outbox_dead_lettered_total`, `sacco_report_materialize_duration_seconds`,
`sacco_report_last_run_timestamp`, `sacco_maker_checker_decisions_total`,
`sacco_maker_checker_self_reject_total`.

(`sacco_backup_age_seconds` is not used in these eight dashboards — it belongs
to the Phase 4 backups operator surface and Task 11's alerting, not a
dashboard panel here.)
