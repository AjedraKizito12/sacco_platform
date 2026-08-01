# Alert: /readyz returning 503

Definition: `infra/observability/logfire/alerts/readyz-503.json`

- **Severity:** critical
- **Status:** **STAGED — NOT ACTIVE.** `source: "unavailable"` in the
  definition file.

## Instrumentation gap

Phase 5 instruments `/readyz`'s per-dependency latency (Task 5) when the
FastAPI process is up and able to serve requests. Logfire is a telemetry
sink for spans/logs/metrics the running process itself emits — it has no
mechanism to poll an HTTP endpoint from outside the app. A process that is
fully down (crashed, out of memory, network-partitioned) emits nothing for
Logfire to alert on. This alert cannot be built from Logfire SQL alerts
alone.

**What's needed to make this active:** an external uptime/synthetic
monitoring product (e.g. Better Uptime, Pingdom, UptimeRobot) or a simple
scheduled cron+curl script polling `GET /readyz` from outside the
deployment, alerting via email on sustained non-200/503 responses. This is
infrastructure tooling outside the scope of Phase 5 (Logfire
instrumentation) — likely a Phase 6 (Rate Limiting & Abuse Protection) or
general infra/ops follow-up.

## If this alert becomes active in the future

- **Trigger condition (as designed):** `/readyz` returns 503 continuously
  for more than 2 minutes.
- **Likely causes:** a dependency `/readyz` checks (Postgres, Redis,
  RabbitMQ, Elasticsearch) is unreachable; the app process itself crashed
  or is deadlocked; a bad deploy broke startup.
- **Response steps:** check `/readyz`'s JSON body for which dependency
  failed; check that dependency's container/service health directly;
  check recent deploys; restart the affected service or roll back.
- **Escalation:** page on-call immediately — a failing readiness probe
  usually means the load balancer/orchestrator is already pulling instances
  out of rotation, i.e. a live outage.
