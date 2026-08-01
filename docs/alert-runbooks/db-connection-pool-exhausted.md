# Alert: Database connection pool exhausted

Definition: `infra/observability/logfire/alerts/db-connection-pool-exhausted.json`

- **Severity:** critical
- **Status:** **STAGED — NOT ACTIVE.** `source: "unavailable"` in the
  definition file.

## Instrumentation gap

Phase 5 ships SQLAlchemy span instrumentation
(`logfire.instrument_sqlalchemy(enable_commenter=False)`), which captures
query shape and duration per statement — but no gauge for
connection-pool utilization (checked-out vs. available connections) and no
server-side Postgres exporter (`pg_stat_activity` connection counts,
`pg_stat_statements`). Neither exists anywhere in this codebase today.

**What's needed to make this active:** either (a) an application-level
gauge reading `AsyncEngine.pool.status()` / `pool.checkedout()` emitted
periodically as a new `sacco_db_pool_*` metric (would follow the same
pattern as `record_business_gauges`), or (b) a dedicated
`postgres_exporter` sidecar shipping Postgres-side connection metrics to
Logfire. Either is new instrumentation work beyond Phase 5's scope.

## If this alert becomes active in the future

- **Trigger condition (as designed):** checked-out connections sustained
  at or near `pool_size + max_overflow` for 5+ minutes.
- **Likely causes:** a connection leak (a session opened without being
  closed/returned — check for missing `async with` / dependency
  cleanup); a slow query holding connections open under load; pool size
  configured too small for actual concurrency; a spike in tenant traffic
  overwhelming the shared pool.
- **Response steps:** check for recently deployed code paths that open a
  session without the standard `get_tenant_session`/`get_platform_session`
  dependency pattern; check for long-running transactions; consider a
  temporary pool-size increase as a stopgap while root-causing.
- **Escalation:** pool exhaustion causes cascading request failures/latency
  platform-wide — treat as equivalent severity to the `api-error-rate`
  alert once active.
