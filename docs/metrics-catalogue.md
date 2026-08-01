# Metrics Catalogue

Every custom `sacco_*` OTel instrument emitted by this platform, cross-checked
against the handle declarations in `app/core/observability/metrics.py` (the
single source of truth — this document describes it, it doesn't define it).

All instruments are created via `logfire.metric_gauge` /
`logfire.metric_counter` / `logfire.metric_histogram`, so they follow OTel's
gauge/counter/histogram semantics: gauges are last-write-wins per label set,
counters are monotonically increasing, histograms record individual
observations that Logfire buckets/quantiles at query time.

## Business gauges (emitted by `record_business_gauges`, the observability beat)

These are computed by `compute_business_gauges` (pure, read-only, testable
offline) and pushed to Logfire by `record_business_gauges` on a beat
schedule. See `app/core/observability/beat.py` for the schedule and
`app/workers/celery_app.py` for the beat registration.

| Metric | Type | Labels | Source / how computed |
|---|---|---|---|
| `sacco_tenants_total` | gauge | `status` | Count of `platform.tenants` rows grouped by `status` (active/suspended/provisioning/etc.). |
| `sacco_subscriptions_total` | gauge | `status` | Count of `platform.subscriptions` rows grouped by `status`. |
| `sacco_subscriptions_mrr` | gauge | `currency` | Sum of `subscription_plans.base_price` joined to subscriptions with `status IN (active, trialing)`, grouped by plan `currency`. Counts only `active`+`trialing` — matches the `dashboard-stats` MRR convention in the Platform_ module contracts. |
| `sacco_invoices_outstanding` | gauge | `status` | Count of `platform.invoices` rows with `status IN (issued, partial, overdue)`, grouped by `status`. |
| `sacco_backup_age_seconds` | gauge | *(none)* | `extract(epoch, now() - max(finished_at))` over `platform.backup_runs` where `status='succeeded'`. When no succeeded run exists yet, reports a ~1-year sentinel (`NO_BACKUP_AGE_SENTINEL`) rather than 0, so a total absence of backups reliably trips the backup-age alert instead of reading as healthy. |
| `sacco_outbox_queue_depth` | gauge | `schema` | Count of outbox events with `published_at IS NULL AND is_dead_lettered = false`, computed once for `schema="platform"` (`platform.PlatformOutboxEvent`) and once per active tenant schema (`TenantOutboxEvent`, `SET LOCAL search_path`). Genuinely per-tenant sliceable. |
| `sacco_loans_total` | gauge | `status` | Count of `loans` rows grouped by `status`, computed per tenant schema and then **summed across all schemas** before being set (`_accumulate_loan_counts`) — because an OTel gauge is last-write-wins per label set, setting `status=X` once per schema would leave only the last schema's count. This is a platform-wide aggregate, NOT sliceable to a single tenant. |

## Flow counters/histograms (Task 9 — instrumented at call sites)

Thin additive instrumentation added directly in the outbox worker,
maker-checker service, reporting beat, and the three auth services
(platform/tenant/member). Labels are outcomes/types/schema only — never PII,
member ids, or amounts.

| Metric | Type | Labels | Source / how computed |
|---|---|---|---|
| `sacco_auth_login_attempts_total` | counter | `outcome`, `actor_type` | Incremented once per login attempt in `app/modules/iam/{platform_auth,tenant_auth,member_auth}/service.py`. `outcome` is one of `success` / `invalid_credentials` / `locked`. `actor_type` is `platform_user` / `tenant_user` / `member`. |
| `sacco_outbox_publish_duration_seconds` | histogram | *(none)* | Recorded in `app/core/outbox/worker.py` around each RabbitMQ publish call. Unlabeled — aggregates across platform + all tenant schemas and all event types. |
| `sacco_outbox_dead_lettered_total` | counter | *(none)* | Incremented in `app/core/outbox/worker.py` when an event exceeds its max publish attempts and is moved to dead-letter state. Unlabeled — one platform-wide series. |
| `sacco_report_materialize_duration_seconds` | histogram | `report_type` | Recorded in `app/modules/reporting/beat.py` around each reporting beat task's materialization. `report_type` is the report name (loan portfolio, income statement, savings statement, fee collection). |
| `sacco_report_last_run_timestamp` | gauge | `report_type` | Set to `time.time()` at the end of each successful reporting beat task run, one series per `report_type`. A stalled beat task shows as a flat/stale value. |
| `sacco_maker_checker_decisions_total` | counter | `outcome` | Incremented in `app/modules/maker_checker/service.py` when `ApprovalService.approve()`/`reject()` completes. `outcome` is `approved` or `rejected`. Says nothing about requests still `pending` — see the alert-runbooks honesty note below. |
| `sacco_maker_checker_self_reject_total` | counter | *(none)* | Incremented in `app/modules/maker_checker/service.py` when a self-approval/self-rejection attempt is blocked. Unlabeled. |

## Golden signals: NOT custom metrics

Request rate, HTTP error rate, and latency percentiles (the three "golden
signals") are **not** emitted as `sacco_*` metrics. They come entirely from
Logfire's auto-instrumented FastAPI spans (`logfire.instrument_fastapi()`,
wired in `app/core/observability/instrument.py`, Phase 5 Increment 1). Every
dashboard/alert that references request rate, 5xx rate, or latency
percentiles queries HTTP server span attributes/duration directly — there is
intentionally no custom counter/histogram duplicating what the span data
already provides.

Similarly, Celery background-job run rate/success/duration comes from
auto-instrumented Celery task spans (`logfire.instrument_celery()`), and
SQLAlchemy query shape/duration comes from auto-instrumented SQLAlchemy spans
(`logfire.instrument_sqlalchemy(enable_commenter=False)`) — no bind
parameters captured.

## Alert signals NOT yet emitted (honesty section)

The following signals a monitoring plan would naturally want are **not**
emitted by anything shipped in Phase 5. Each has a staged `"source":
"unavailable"` alert definition in `infra/observability/logfire/alerts/`
describing exactly what instrumentation is missing, rather than a query that
could never fire or would always false-positive:

- **`/readyz` 503 sustained** — Logfire has no external prober; a fully-down
  process emits nothing for Logfire to see. Needs an external uptime-check
  tool (synthetic monitor or cron+curl+alert).
- **Database connection-pool exhaustion** — no pool-utilization gauge and no
  Postgres server-side exporter (`pg_stat_activity`, `pg_stat_statements`)
  ship in Phase 5.
- **Any beat task (beyond reporting) missing its schedule** — only
  `sacco_report_last_run_timestamp` exists, scoped to the reporting beat
  tasks. Notification dispatch, key rotation, business-gauge emission,
  search reconciliation, the deleted-doc sweep, and subscription
  past-due/suspension sweeps have no last-run gauge.
- **Approvals pending too long** — `sacco_maker_checker_decisions_total` is a
  decision counter (fires only at approve/reject time), not a pending-age
  gauge. There is no signal for "this request has been open N hours."

See `docs/alert-runbooks/` for the per-alert response runbook, including the
four staged/unavailable ones.
