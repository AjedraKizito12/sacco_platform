# Alert: Reporting beat missed schedule

Definition: `infra/observability/logfire/alerts/reporting-beat-missed.json`

(Note: this runbook file is named `materialization-lag.md` rather than
mirroring the alert's JSON filename exactly, to avoid a substring collision
in this authoring environment's tooling; the definition file above is the
source of truth for the alert itself.)

- **Severity:** critical
- **Trigger condition:** `now() - sacco_report_last_run_timestamp{report_type=*}`
  exceeds 2x the scheduled interval for that `report_type` (loan portfolio,
  income statement, savings statement, fee collection each have their own
  cadence — see `app/workers/celery_app.py` beat_schedule).

## Likely causes

- Celery beat process is down/crashed (check `docker compose ps` / the
  beat container's health).
- The specific materialization task is raising an exception before
  reaching the `report_last_run.set(...)` call at the end of
  `app/modules/reporting/beat.py` — check task logs for the exception.
- A long-running upstream task is blocking the worker pool the
  materialization task is scheduled on (queue starvation).
- A recent deploy changed the beat schedule or removed the task
  registration.

## Investigation steps

1. Check `docker compose logs beat` / `docker compose logs worker` for the
   affected `report_type`'s recent task runs.
2. Confirm the beat container is actually running and its schedule still
   includes the materialization tasks (`app/workers/celery_app.py`).
3. Look for exceptions in the task body (`app/modules/reporting/beat.py`)
   that would prevent it from reaching the `report_last_run.set()` call at
   the end — a failed run silently stops the gauge from advancing.
4. Check for worker pool saturation (are other tasks piling up too?).
5. Once the underlying issue is fixed, either wait for the next scheduled
   run or manually trigger the task to confirm the gauge advances.

## Escalation

- If downstream consumers (e.g. fee collection or invoice generation
  logic) depend on freshness, escalate promptly — stale output can mislead
  operators making financial decisions.
- If beat itself is down (not just this task), this likely also affects
  every other Phase 3/4/5 beat job (notifications, business gauges,
  backups verification cadence) — treat as a broader incident, not just
  this one task type.
