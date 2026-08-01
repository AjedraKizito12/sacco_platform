# Alert: Background beat task missed schedule (general)

Definition: `infra/observability/logfire/alerts/beat-task-missed-general.json`

- **Severity:** critical
- **Status:** **STAGED — NOT ACTIVE.** `source: "unavailable"` in the
  definition file.

## Instrumentation gap

The only last-run gauge Phase 5 emits is `sacco_report_last_run_timestamp`,
scoped exclusively to the reporting beat tasks (see the
`reporting-beat-missed` alert / `materialization-lag.md` runbook for the
backed version of this alert covering that one case). Every other
scheduled Celery beat task in this platform — notification dispatch, RSA
signing-key rotation, business-gauge emission
(`record_business_gauges` itself), search-index reconciliation, the
deleted-doc sweep, subscription past-due/suspension sweeps, fee
assessment — has no last-run gauge at all.

**What's needed to make this active:** a shared "beat task heartbeat" gauge
(e.g. `sacco_beat_task_last_run_timestamp{task_name=*}`) instrumented once
at the end of every registered beat task, following the exact pattern
`sacco_report_last_run_timestamp` already establishes. This is
straightforward follow-up work but was out of scope for Phase 5's
committed instrumentation set.

## If this alert becomes active in the future

- **Trigger condition (as designed):** no recorded run within 2x a given
  task's scheduled interval, for any `task_name`.
- **Likely causes:** Celery beat process down; the specific task raising
  before completion; worker pool starvation; a deploy that dropped the
  task's beat-schedule registration.
- **Response steps:** check `docker compose logs beat`/`worker`; confirm
  `app/workers/celery_app.py`'s `beat_schedule` still registers the task;
  check for exceptions in the task body.
- **Escalation:** treat with the same urgency as
  `materialization-lag.md` — a stalled beat task silently degrades a
  cross-cutting concern (notifications, security key rotation, search
  freshness, billing dunning) without any user-facing error, so it can go
  unnoticed for a long time without this alert.
