# Alert: Outbox dead-letter growth

Definition: `infra/observability/logfire/alerts/outbox-dead-letter-growth.json`

- **Severity:** critical
- **Trigger condition:** `sacco_outbox_dead_lettered_total` (unlabeled
  counter, platform + all tenant schemas combined) increases at all within
  the trailing hour.

## Likely causes

- RabbitMQ was unreachable/down for longer than the outbox worker's max
  retry window, so events exhausted their publish attempts.
- A malformed event payload that a consumer (or RabbitMQ itself, e.g. a
  queue with a strict schema/size limit) rejects on every attempt.
- A RabbitMQ queue/exchange misconfiguration (wrong routing key, missing
  binding) that always fails to route.
- The outbox worker crashed/restarted repeatedly mid-publish, exhausting
  attempts before succeeding (check worker container logs/restarts).

## Response steps

1. Open the Outbox dashboard (`outbox.json`) — check the dead-lettered rate
   panel to see whether this was a single burst or ongoing.
2. Query `platform.platform_outbox_events` / the equivalent tenant-schema
   table for rows with `is_dead_lettered = true` in the affected window;
   inspect `event_type` and payload to identify the pattern.
3. Check RabbitMQ health (`docker compose logs rabbitmq`, management UI if
   available) for the same window — was it down, or refusing connections?
4. Check outbox worker logs for repeated publish failures/exceptions
   immediately before the dead-letter timestamps.
5. Once the root cause is fixed, dead-lettered events require **manual
   replay** — there is no automatic retry once dead-lettered (append-only;
   do not delete/update rows directly per the outbox contracts in
   CLAUDE.md). Replay via whatever the outbox module's documented replay
   path is (check `app/core/outbox/` for a replay script/entrypoint before
   hand-rolling one).

## Escalation

- Any dead-lettered event represents at-least-once-delivery FAILURE for
  that event (a domain event, e.g. a notification or a cross-module
  signal, never reached its consumer). Page on-call immediately — do not
  wait for a batch to accumulate.
- If the cause is a RabbitMQ outage, coordinate with infra/ops on RabbitMQ
  recovery before attempting replay.
