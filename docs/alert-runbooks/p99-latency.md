# Alert: API p99 latency high

Definition: `infra/observability/logfire/alerts/p99-latency.json`

- **Severity:** critical
- **Trigger condition:** p99 HTTP server span duration exceeds 5 seconds
  over a trailing 10-minute window, across all tenant schemas.

## Likely causes

- A slow/N+1 database query introduced by a recent change (check the
  Database dashboard's slow-query panel — span-based, `database.json`).
- Database contention: lock waits, a long-running transaction blocking
  others, or connection pool saturation.
- An external dependency call (RabbitMQ publish, Elasticsearch query,
  outbound HTTPX call) is slow or timing out.
- A large report/PDF generation (reporting or billing invoice PDFs) run
  synchronously in the request path rather than via beat/background task.
- Elevated load from one tenant (check `single-tenant-traffic-share`) that
  degrades shared resources for everyone.

## Response steps

1. Open the Database dashboard and identify the slowest query/statement
   shapes in the same window.
2. Check the Platform Overview latency panel for whether this is a spike
   (single slow deploy/query) or a sustained plateau (resource exhaustion).
3. Check Postgres for long-running transactions / lock waits
   (`pg_stat_activity`, `pg_locks`) if DB-side.
4. Check outbox queue depth and publish-duration dashboards — a RabbitMQ
   slowdown can back up request-time synchronous operations if any path
   incorrectly does synchronous work that should be outboxed.
5. Identify whether one `tenant_schema` or one route (`http.route` span
   attribute) dominates the slow requests.
6. If a specific endpoint is implicated, check whether it does synchronous
   PDF rendering (WeasyPrint) or a heavy aggregate query that should be
   cached/paginated.

## Escalation

- If unresolved within 20 minutes or p99 keeps climbing: page the on-call
  engineer.
- If isolated to one tenant/route with a clear fix (e.g. add an index,
  paginate a query), file a follow-up ticket and monitor rather than
  treating as an ongoing incident once mitigated.
