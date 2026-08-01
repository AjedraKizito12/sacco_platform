# Alert: Overdue invoices growing

Definition: `infra/observability/logfire/alerts/overdue-invoices-growth.json`

- **Severity:** warning
- **Trigger condition:** `sacco_invoices_outstanding{status="overdue"}`
  grows more than 10% compared to its value 24 hours ago.

## Likely causes

- A wave of tenants failing to pay (broad economic/billing-cycle effect,
  not necessarily a platform bug).
- `PaymentService` or the invoice-status transition logic has a bug
  keeping invoices from moving out of `overdue` after payment.
- The subscription-gate/dunning cadence (grace period logic in
  `get_tenant_session`) is misconfigured, so tenants aren't being warned
  before they slip into `overdue`.
- A payment processor issue (`OfflineProcessor` is the only live one in
  v1) means recorded payments aren't reaching confirmation.
- Notification delivery for `invoice_overdue` events is broken, so
  tenants aren't being alerted to pay (check the notifications dashboard /
  `notification_events` table for delivery failures).

## Response steps

1. Open the Billing dashboard (`billing.json`) and check the overdue trend
   panel to confirm the growth and its shape (sudden jump vs. steady
   climb).
2. Query `platform.invoices` for rows with `status='overdue'` ordered by
   `due_date` — look for a cluster around a specific billing period or
   tenant cohort.
3. Check whether `Payment` rows are stuck `pending` (unconfirmed) for the
   same invoices — this would point at a maker-checker approval backlog
   (`billing.confirm_payment`) rather than tenants not paying at all.
4. Check the notifications pipeline for `invoice_overdue` delivery
   failures if this looks like tenants weren't warned.
5. If this is a genuine payment-collection issue (not a bug), this is a
   finance/support workflow question, not an engineering incident —
   route to finance staff for tenant follow-up.

## Escalation

- If growth correlates with a code/infra bug (payments not confirming,
  notifications not sending), escalate to on-call engineering.
- If growth is organic (tenants not paying), route to finance/billing
  ops — no engineering action needed beyond confirming the pipeline itself
  is healthy.
