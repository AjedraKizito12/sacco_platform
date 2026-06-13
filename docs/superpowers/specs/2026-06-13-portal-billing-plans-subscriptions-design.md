# Portal Billing — Plans + Subscriptions (SP15) Design

**Date:** 2026-06-13
**Phase:** 2 (Admin Portal), sub-plan 15
**Status:** Approved

## Goal

Add the **Plans** and **Subscriptions** screens of the Billing nav group to the
admin portal, plus the tenant-context **assign-plan** flow deferred from SP14.
Invoices and payments (record/void/pending-confirmation queue) are explicitly
**out of scope** and become SP16.

## Contract posture

Pure portal client work. **Zero new backend endpoints, api-client methods,
Zod schemas, permission keys, or StatusBadge maps** — all already exist:

- **api-client** (`resources.billing.*`): `listPlans/createPlan/getPlan/patchPlan`,
  `listSubscriptions/getSubscription/createSubscription/cancelSubscription/reactivateSubscription`;
  and `resources.tenants.assignPlan`.
- **schemas** (`@sacco/schemas` `billing.ts`): `subscriptionPlanSchema`,
  `subscriptionPlanPatchSchema`, `subscriptionCreateSchema`,
  `subscriptionCancelSchema` (+ inferred `*Input` types).
- **permissions** (`permissions.ts`): `billing.read` → finance, `billing.write` → admin.
- **StatusBadge**: `SUBSCRIPTION_STATUS` map (entity `"subscription"`).
- **Sidebar**: a "Billing" item already points at `/platform/billing/plans`.

This mirrors the SP12–14 posture (Phase 2 contract B: no new endpoints).

## Backend facts (authoritative)

- `GET /platform/billing/plans` (finance) is **unpaginated** → list table uses the
  in-memory DataTable adapter (same as SP12 UsersTable). `only_active` query filter.
- `POST/PATCH /platform/billing/plans` (admin) are **direct** (no maker-checker).
- `GET /platform/billing/subscriptions` (finance) supports `tenant_id` and
  `status_filter` query params.
- `POST /platform/billing/subscriptions/{id}/cancel` takes `mode=at_period_end`
  (soft, **direct**, reversible) or `mode=immediate` (**maker-checker** via the
  `billing.cancel_subscription` executor). Body: `{reason (≥2 chars), cancel_at_period_end}`.
- `POST /platform/billing/subscriptions/{id}/reactivate` (admin) — direct,
  suspended → active.
- `POST /platform/tenants/{id}/assign-plan` (admin) and
  `POST /platform/billing/subscriptions` both delegate to
  `SubscriptionService.assign(tenant_id, plan_id, start_date)` and return
  `SubscriptionOut` (201). 409 if a live subscription already exists or the plan
  is inactive; 404 if tenant/plan unknown. SP15 uses the **tenant-context** path.
- `SubscriptionOut` carries `tenant_id`/`plan_id` only — **no embedded names**.

## Plan fields (from `SubscriptionPlanIn`)

`code` (2–64), `name`, `description?`, `currency` (default UGX),
`base_price` (≥0), `per_user_price`, `per_member_price`, `billing_period`
(monthly|quarterly|annual), `member_limit?`, `user_limit?`,
`trial_period_days` (≥0), `grace_period_days` (default 30), `is_active`.
`features` (free-form dict) is **not surfaced** in the v1 form (YAGNI — all v1
plans default it empty; revisit if a real plan needs it).

## Screens (7)

All under `app/platform/(authed)/billing/*` except assign-plan.

1. **Plans list** `/platform/billing/plans` — DataTable (in-memory adapter over
   `listPlans`). Columns: name, code, base price (`<Money>`), billing period,
   active. `only_active` filter slot. Gated `billing.read`.
2. **Plan detail** `/platform/billing/plans/[id]` — overview card, `<AuditBar>`
   placeholder, Edit action (shown when `billing.write`).
3. **New plan** `/platform/billing/plans/new` — RHF + `subscriptionPlanSchema`
   → `createPlan`; direct; toast + redirect to detail. Gated `billing.write`.
4. **Edit plan** `/platform/billing/plans/[id]/edit` — RHF +
   `subscriptionPlanPatchSchema` → `patchPlan`; direct. Gated `billing.write`.
5. **Subscriptions list** `/platform/billing/subscriptions` — DataTable over
   `listSubscriptions`. Columns: tenant (link to tenant detail), plan, status
   (`<StatusBadge entity="subscription">`), current period, next billing.
   Status + tenant filters. Gated `billing.read`.
   **Name resolution:** map `plan_id → plan.name` from the (small) plans list;
   render tenant as a link to `/platform/tenants/{tenant_id}` with the label
   resolved from the tenants list (SP13 `listTenants`). IDs are the fallback
   label if a lookup misses.
6. **Subscription detail** `/platform/billing/subscriptions/[id]` — overview +
   actions: **Cancel** with both modes — `at_period_end` via base
   `<ConfirmDialog>` (direct, reversible), `immediate` via
   `<MakerCheckerConfirmDialog>` (locked copy, creates approval) — and
   **Reactivate** (direct, suspended only). All `billing.write`.
7. **Assign plan** `/platform/tenants/[id]/assign-plan` + an "Assign plan"
   button on `TenantActions` (gated `billing.write`). Form: plan picker
   (`<Select>` populated from active plans) + optional start_date
   (`<DateInput>`) → `tenants.assignPlan`. 409 → toast ("tenant already has a
   live subscription" / "plan inactive"); success → toast + redirect to the new
   subscription detail.

## Sub-nav

The single sidebar "Billing" item stays. A lightweight tab strip
(**Plans | Subscriptions**) renders at the top of the billing pages so both
sections are reachable without a second sidebar item. (Confirmed with user.)

## Maker-checker / confirm UX

Per established contracts (K/V): the immediate-cancel button is labelled
"Request …" and routes through `<MakerCheckerConfirmDialog>`; soft cancel and
reactivate use the base `<ConfirmDialog>`. PR #26 feedback pattern: dialog
closes on success only, `toast.success`/`toast.error` via `apiErrorMessage`.

## Money / dates / status

`<Money amount currency />` for all prices (plans carry their own `currency`).
`<FormattedDate>` for period/billing dates. `<StatusBadge entity="subscription">`
for subscription status. No raw `toLocaleString` (contract H/R/S).

## Out of scope (documented)

- Invoices + payments (list/detail/PDF/void/record/pending-confirmation/reject) → SP16.
- `features` dict editing on the plan form (YAGNI).
- e2e (seeded-backend sub-plan) and next-intl (portal-wide deferral) — raw English strings.
- `<MakerCheckerBanner>` on subscription detail (needs the approvals-list endpoint, SP17).

## Testing

Vitest + Testing Library per screen/form, mirroring SP12–14: schema tests
(if any new helper schema is added for assign-plan), list-table render,
form validation + submit + error paths, cancel-mode branching, assign-plan
409 handling. `typecheck` + `lint` clean across `@sacco/schemas`/`@sacco/ui`/`@sacco/portal`.
All changes confined to `admin/` + `docs/` (contracts B/N).
