# Portal — Platform Approvals Inbox (SP17) Design

**Date:** 2026-06-16
**Phase:** 2 (Admin Portal), sub-plan 17
**Status:** Approved

## Goal

Build the platform Approvals inbox so a second operator can act on the
maker-checker requests that SP14/SP15/SP16 can only *create*. Three screens —
inbox list, request detail (with approve / reject / cancel), and
"my submissions" — backed by the existing `/platform/approvals/*` router.

This unblocks the approve half of every platform maker-checker flow:
`billing.confirm_payment`, `billing.void_invoice`,
`billing.cancel_subscription`, `platform_user.update_sensitive`,
`tenant.suspend`, `tenant.retry_provisioning`, `platform.start_impersonation`.

## Contract posture (read first — this sub-plan is NOT pure-client)

Unlike SP12–SP16, SP17 includes a **small backend response-shape
enrichment**. This was an explicit decision during brainstorming: the roadmap's
"1 of 2 approvals" quorum badge and an approver audit trail are not expressible
from the current `ApprovalRequestOut`, which exposes `required_approvals` but
**no current-approval count and no actions list** — and there is no endpoint to
list a request's actions.

Per CLAUDE.md contract B ("All backend additions ship in Phase 1.7. If a
sub-plan thinks it needs a new endpoint, stop and surface"): we surfaced it. The
chosen resolution is an **additive** change (no new endpoints, no renamed/removed
fields), treated as a Phase-1.7-style backend task. It ships in its own commits
and is **not** mixed with the `admin/`-only portal commits, preserving the spirit
of contracts B/N. The backend part lands first; the portal consumes it.

Everything already in place (no change needed):

- **api-client** (`resources.makerChecker.*`): `listPlatform(query)`,
  `getPlatform(id)`, `submitPlatform(body)`, `approvePlatform(id, body)`,
  `rejectPlatform(id, body)`, `cancelPlatform(id, body)`. All carry the
  `as never` / `Promise<never>` wart — cast to `{ data?, error? }` per SP15/16.
- **queryKeys** (`query-keys.ts`): `approvals.platform(filters)`,
  `approvals.detail(id)`, `approvals.root()`.
- **StatusBadge**: `APPROVAL_REQUEST_STATUS` (entity `"approval_request"`) maps
  all seven statuses: `pending`, `approved`, `rejected`, `executed`,
  `execution_failed`, `expired`, `cancelled`.
- **@sacco/ui**: `MakerCheckerConfirmDialog`, `ConfirmDialog`, `DataTable`,
  `FormField`, `Textarea`, `Money`, `FormattedDate`/`FormattedDateTime`,
  `AuditBar`. `MakerCheckerBanner` exists (consumed by the deferred banner-wiring
  follow-up, not SP17).
- **permissions** (`permissions.ts`): `approvals.read` → support,
  `approvals.approve` → admin.

New in this sub-plan: the `@sacco/schemas` approval Out types + operation-label
map + action Zod inputs (none exist yet), and the three portal screens.

## Backend facts (authoritative)

Router `app/modules/maker_checker/platform_api.py`, prefix `/platform/approvals`:

| Endpoint | Gate | Returns |
|----------|------|---------|
| `GET ""` (`?status=&operation_type=&requested_by=`) | `CurrentSupport` | `list[ApprovalRequestOut]` |
| `GET "/{id}"` | `CurrentSupport` | `ApprovalRequestOut` → **`ApprovalRequestDetailOut`** (this sub-plan) |
| `POST "/{id}/approve"` (body `{comment?}`) | `CurrentAdmin` | `ApprovalRequestOut` |
| `POST "/{id}/reject"` (body `{reason?}`) | `CurrentAdmin` | `ApprovalRequestOut` |
| `POST "/{id}/cancel"` (body `{comment?}`) | `CurrentAdmin` | `ApprovalRequestOut` |
| `POST ""` (submit) | `CurrentAdmin` | not used by SP17 (requests are created by feature flows) |

Service invariants (`app/modules/maker_checker/service.py`):

- **Self-approval is rejected** (`approve()` raises `ValueError` if
  `actor_user_id == requested_by`). The UI mirrors this (see permission rules).
- Quorum: an `approve` action increments the count; when
  `count >= required_approvals` the request transitions `approved` → executor
  runs → `executed` (or `execution_failed`). For all v1 platform operations
  `required_approvals == 1`, so a pending request is "0 of 1" and the first
  approval executes it. The count machinery still exists for future quorum ≥ 2.
- Statuses set by the service: `pending`, `approved`, `rejected`, `cancelled`,
  `executed`, `execution_failed`, `expired` (the last via the Celery beat job).
- `cancel()` is the requester withdrawing their own pending request.
- No double-vote: unique `(approval_request_id, actor_user_id)`.

Operation payloads (drive the detail renderer — none store a "before" state):

| Operation | Payload keys |
|-----------|--------------|
| `platform_user.update_sensitive` | `user_id`, `is_active`, `is_superuser` (new values only) |
| `billing.void_invoice` | `invoice_id`, `reason` |
| `billing.cancel_subscription` | `subscription_id`, `reason` |
| `billing.confirm_payment` | `payment_id` |
| `tenant.suspend` | `tenant_id`, `reason` |
| `tenant.retry_provisioning` | `tenant_id` |
| `platform.start_impersonation` | `platform_user_id`, `tenant_id`, `reason` |

## Part 1 — Backend response enrichment (separate commits)

**Files:** `app/modules/maker_checker/schemas.py`,
`app/modules/maker_checker/platform_api.py` (and the service if a count helper
is extracted). Tenant router (`api.py`) untouched beyond default-0 parity.

1. Add `current_approvals: int = 0` to `ApprovalRequestOut`. The default keeps
   the **shared** tenant router (`api.py`, same schema) valid — it will report
   `0` until the tenant approvals inbox (later sub-plan) wires it. Because
   `current_approvals` is not an ORM attribute, handlers must set it explicitly
   (it cannot arrive via `from_attributes`).
2. Add `ApprovalRequestDetailOut(ApprovalRequestOut)` with
   `actions: list[ApprovalActionOut]` (the existing `ApprovalActionOut` already
   has `id`, `actor_user_id`, `action`, `acted_at`, `comment`). Return it from
   `GET /platform/approvals/{id}` only.
3. `current_approvals` = count of actions with `action == "approve"` for the
   request (reuse the service's existing approval-count logic). The list handler
   computes it per row; the detail handler computes it and loads `actions`.
4. Tests: list returns `current_approvals`; detail returns the actions trail
   with correct ordering; a quorum-2 fixture shows "1 of 2" after one approve.

**Definition of additive:** no endpoint added/removed, no field renamed or
removed, no gate changed. Existing clients keep working; `current_approvals`
defaults to `0`, `actions` appears only on the richer detail response.

## Part 2 — Portal schemas & shared (`@sacco/schemas`)

Hand-written Out types mirroring the enriched Pydantic (same approach as
`InvoiceOut`/`SubscriptionOut`):

- `ApprovalActionOut { id; actor_user_id; action; acted_at; comment }`.
- `ApprovalRequestOut { id; operation_type; payload; requested_by; requested_at;
  required_approvals; current_approvals; status; expires_at; executed_at;
  execution_result; rejection_reason }` (`payload`/`execution_result` typed as
  `Record<string, unknown>`).
- `ApprovalRequestDetailOut extends ApprovalRequestOut { actions: ApprovalActionOut[] }`.
- `PLATFORM_OPERATION_LABELS: Record<string, string>` (e.g.
  `"billing.void_invoice" → "Void invoice"`), with a fallback that humanizes
  unknown operation types so a new backend operation never renders a raw key
  badly (mirrors StatusBadge's unknown-status behavior, contract S).
- `approveActionSchema { comment?: string }` and
  `rejectActionSchema { reason: string (min length) }` Zod inputs (+ inferred
  `*Input` types). Cancel needs no body fields (optional comment omitted in v1).

## Part 3 — Portal screens (`admin/` only)

All three pages fetch server-side via `getPlatformPageContext()` +
`requirePlatformPermission(user, "approvals.read")`, following the SP12/16
server-fetch pattern. The platform sidebar already links `/platform/approvals`
(gated `approvals.read`) — these pages fill the current 404.

### `/platform/approvals` — inbox

- Server: `listPlatform({})` + `admin.listUsers()` for requester-name
  resolution (Map<id,email/name>, same pattern as SP15/16 name resolution).
- `<ApprovalsTable rows={…} />`: in-memory `<DataTable>` adapter (DataTable is
  hardwired server-side mode; the list endpoint is unpaginated → in-memory
  filter/sort/paginate, exactly like SP16 InvoicesTable). Columns: **Operation**
  (labelled via `PLATFORM_OPERATION_LABELS`, links to detail), **Status**
  (`<StatusBadge entity="approval_request">`), **Quorum** (`{current} of
  {required}`), **Requested by** (resolved name), **Requested**
  (`<FormattedDate>`). Filters: status + operation_type `<Select>` slots.
- Tests must mock `useTableUrlState` (nuqs has no resolvable test adapter under
  pnpm strict isolation — established SP16 pattern).

### `/platform/approvals/[id]` — detail

- Server: `getPlatform(id)` → `ApprovalRequestDetailOut`; `notFound()` if absent.
  Resolve requester + each action actor via `admin.listUsers()`.
- Layout: header (operation label + status badge + quorum) → **operation-aware
  payload renderer** → **actions trail** → action buttons → `<AuditBar
  entityType="approval_request" entityId={id} />`.
- **Operation-aware payload renderer** (honors the "diff renderer" decision):
  - Base: a structured, typed tree (`<PayloadView>`) — formats UUIDs as
    monospace, booleans as yes/no, `reason` as text, with a "view raw JSON"
    toggle. Generic over any payload shape so unknown operations still render.
  - Enhancement: for `platform_user.update_sensitive` ONLY, render a
    **before → after** diff. The "before" is fetched server-side
    (`admin.getUser(payload.user_id)`); changed fields (`is_active`,
    `is_superuser`) show old → new. No other operation carries a before-state,
    so they render as the structured tree (documented, not a gap).
- **Actions trail**: each `ApprovalActionOut` as actor (resolved) + action
  (approve/reject) + `<FormattedDateTime>` + comment.
- **Action buttons (maker-cannot-approve UI rules):**
  - Approve / Reject: shown only when `status == "pending"` **and**
    `currentUser.id !== requested_by` **and** user has `approvals.approve`.
    Both use the **base `<ConfirmDialog>`** — NOT `<MakerCheckerConfirmDialog>`,
    whose locked copy ("creates an approval request, not execute") is the
    *maker* side that lives in the feature flows. The inbox is the *checker*
    side: approving **executes** the operation. Approve → confirm dialog with an
    optional comment field and copy stating the operation will run on approval.
    Reject → `ConfirmDialog` (`destructive`) with a required-reason field.
  - When `currentUser.id === requested_by`: hide approve/reject, show an
    explanatory tooltip ("You submitted this request and cannot approve your own
    request"), and show **Cancel** (pending only) → `ConfirmDialog`
    (`destructive`) → `cancelPlatform(id)`.
  - All mutations via `useTypedMutation`, invalidating
    `approvals.platform()` + `approvals.detail(id)`, with success/error toasts
    (`apiErrorMessage`) and `router.refresh()`, per SP16.

### `/platform/approvals/my-submissions`

- The same `<ApprovalsTable>` fed `listPlatform({ requested_by: user.id })`.
  Distinct page (own route) so the operator can bookmark their queue; the table
  component is shared.

## Permission mapping (authoritative — drives UI gating)

| Action | Backend gate | Portal gate |
|--------|--------------|-------------|
| List / detail / my-submissions | `CurrentSupport` | `approvals.read` |
| Approve / Reject | `CurrentAdmin` + self-approval rejected | `approvals.approve` + `currentUser != requested_by` |
| Cancel | `CurrentAdmin` (requester withdraws) | `currentUser == requested_by` + pending |

UI gating is UX-only; the API enforces (contract D). The self-approval rule is
the one place the UI must mirror a service invariant to avoid a guaranteed-400
button.

## Out of scope (deferred)

- **`<MakerCheckerBanner>` wiring on invoice / subscription / tenant detail
  pages** — split into its own follow-up sub-plan (per this brainstorm). Those
  pages keep their SP14/15/16 deferral notes until then. The enriched
  `current_approvals` shipped here is what unblocks that follow-up.
- **Tenant-side approvals inbox** — later sub-plan; only `current_approvals`
  default-0 parity is touched on the shared schema here.
- **Diff annotations for operations other than `update_sensitive`** — no
  before-state exists in their payloads.
- **e2e + next-intl** — portal-wide deferrals (raw English), matching SP12–16.
- **submit/create from the portal** — requests are created by the feature flows
  (billing, tenants, users), never hand-authored in the inbox.

## Testing strategy

- **Backend:** pytest for `current_approvals` count + `actions` trail +
  quorum-2 "1 of 2" (real Postgres, project convention).
- **Portal:** Vitest + Testing Library. `ApprovalsTable` (row render, link,
  quorum text, empty state — `useTableUrlState` mocked); detail action
  components (approve optional-comment, reject required-reason, cancel
  visibility, self-approval hides approve + shows tooltip);
  `PayloadView`/diff renderer (update_sensitive before→after; generic tree for a
  non-update op). Per-package `test` + `typecheck` + `lint` green; all portal
  changes under `admin/`.
