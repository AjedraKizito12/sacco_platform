# Alert: API error rate high

Definition: `infra/observability/logfire/alerts/api-error-rate.json`

- **Severity:** critical
- **Trigger condition:** HTTP 5xx responses exceed 5% of all HTTP server
  spans over a trailing 5-minute window, across all tenant schemas.

## Likely causes

- A recent deploy introduced a regression (check the deploy timestamp
  against the window start).
- A downstream dependency is failing (Postgres, Redis, RabbitMQ,
  Elasticsearch) and requests are raising unhandled exceptions.
- A specific tenant schema is unprovisioned/misconfigured and every request
  against it 500s (check `single-tenant-traffic-share` and the
  tenant-drilldown dashboard for a concentration in one `tenant_schema`).
- Database connection pool exhaustion (see the `db-connection-pool-exhausted`
  staged alert — no live signal for this yet, but check pool errors in logs
  manually).
- A third-party/library upgrade changed error behavior.

## Response steps

1. Open the Platform Overview dashboard (`platform-overview.json`) and
   confirm the 5xx rate panel corroborates the alert; check whether it's a
   sharp spike (deploy/dependency outage) or a slow climb (creeping
   resource exhaustion).
2. Check the Logfire Explore/Issues view for the actual exceptions
   (`query_find_exceptions_in_file` / `issue_list`) grouped by fingerprint —
   identify the dominant error type.
3. Cross-reference with the tenant-drilldown dashboard: is this
   platform-wide or concentrated in one `tenant_schema`?
4. Check recent deploys/migrations. If a deploy correlates, roll back.
5. Check dependency health (`docker compose ps`, Postgres/Redis/RabbitMQ/ES
   logs) if no code correlation is found.
6. If the cause is a specific tenant's bad data/state, consider whether the
   subscription gate or a data-integrity issue is involved before treating
   it as a platform-wide incident.

## Escalation

- If unresolved within 15 minutes or the rate keeps climbing: page the
  on-call engineer (this is a production-launch-gating alert per the SaaS
  roadmap — Phase 5/6 exist specifically to catch this).
- If a specific tenant is the sole cause and it's a data/config issue (not a
  platform bug), this can be handled as a support ticket rather than an
  incident once the blast radius is confirmed to be single-tenant.
