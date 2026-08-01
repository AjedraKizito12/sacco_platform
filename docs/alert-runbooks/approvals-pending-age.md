# Alert: Approvals pending too long

Definition: `infra/observability/logfire/alerts/approvals-pending-age.json`

- **Severity:** warning
- **Status:** **STAGED — NOT ACTIVE.** `source: "unavailable"` in the
  definition file.

## Instrumentation gap

`sacco_maker_checker_decisions_total` is a decision counter: it increments
only at the moment `ApprovalService.approve()`/`reject()` completes (see
`app/modules/maker_checker/service.py`). It carries zero information about
requests that are still sitting open in `pending` — there is no way to
derive "how long has this been waiting" from a counter that only fires on
resolution.

**What's needed to make this active:** a new gauge computed from
`platform.approval_requests` / tenant-schema `approval_requests` rows where
`status='pending'` — e.g. `max(now() - created_at)` per `operation_type` —
emitted on a beat schedule (would slot naturally into
`record_business_gauges` or a sibling function). This is new query/beat
work beyond what Phase 5 shipped.

## If this alert becomes active in the future

- **Trigger condition (as designed):** the oldest open approval request
  exceeds 24 hours since submission, for any `operation_type`.
- **Likely causes:** insufficient eligible checkers online/available (see
  the maker-checker quorum rules — self-approval is rejected, so a
  single-maker team can genuinely stall); the approval-pending
  notification (`maker_checker_pending`) not being delivered; an operator
  simply not checking their approval inbox.
- **Response steps:** check the approvals inbox
  (`/platform/approvals` or `/approvals` per audience) for the stuck
  request(s); check notification delivery for `maker_checker_pending`
  events to eligible checkers; if this is a payment confirmation, loan
  approval, or write-off, prioritize by business impact (money-moving
  operations should be resolved fastest).
- **Escalation:** for time-sensitive operations (loan disbursement,
  payment confirmation), a stuck approval directly blocks a member/tenant
  outcome — escalate to the relevant operator/finance team, not
  engineering, since this is a process gap rather than a code fault once
  the underlying pipeline (notifications, quorum) is confirmed healthy.
