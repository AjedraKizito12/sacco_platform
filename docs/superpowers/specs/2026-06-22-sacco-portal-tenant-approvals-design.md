# SACCO Admin Portal — Tenant Approvals Inbox (Phase 3g-2) Design

**Date:** 2026-06-22
**Phase:** 3 (SACCO Admin / tenant-operator portal), sub-plan g (dead-link fills), part 2 — Tenant approvals inbox
**Status:** Approved

## Context

Phase 3g fills three dead tenant sidebar links scaffolded in Phase 2:
- **3g-1 Ledger** — `/ledger/accounts` — **done** (PR #50).
- **3g-2 Tenant approvals inbox** (this doc) — `/approvals` — the maker-checker
  **checker** side.
- **3g-3 Tenant audit** — `/audit` — needs a new tenant-scoped audit endpoint.

Every Phase-3 module so far CREATES tenant maker-checker approval requests but
nothing **approves** them. The eight tenant operation types that submit an
approval are:

| operation_type | label | quorum |
|---|---|---|
| `members.change_status` | Change member status | 1 |
| `savings.withdraw` | Withdraw from savings | 1 |
| `shares.redeem_shares` | Redeem shares | 1 |
| `credit.approve_application` | Approve loan application | 1 |
| `credit.write_off` | Write off loan | 2 (above threshold) |
| `credit.restructure_schedule` | Restructure loan schedule | 2 |
| `credit.apply_payroll_batch` | Apply payroll batch | 1 |
| `ledger.post_journal_entry` | Post manual GL entry | 1 |

3g-2 builds the operator-facing inbox + detail + approve/reject/cancel actions,
mirroring the platform approvals inbox (SP17). It is the tenant-side twin of
`app/platform/(authed)/approvals/*`.

## Backend facts (small additive parity change)

The tenant `/approvals` router (`app/modules/maker_checker/api.py`) already
exposes submit / list / get / approve / reject / cancel, gated on
`CurrentTenantUser`, schema-agnostic via `ApprovalService`. **But the list and
get endpoints lag the platform SP17 versions:**

- `list_approvals` does plain `ApprovalRequestOut.model_validate(r)` →
  `current_approvals` is always 0 (it is computed via
  `ApprovalService.approval_count`, **not** a column), and there is no
  `requested_by` filter or ordering.
- `get_approval` returns plain `ApprovalRequestOut` (no `actions` trail).

3g-2 brings the tenant endpoints to **parity with the platform ones** — a small,
additive change, no new endpoints, no renamed/removed fields, no gate change:

1. `GET /approvals` — add `requested_by: uuid.UUID | None` query filter, order
   by `requested_at DESC`, and enrich each row's `current_approvals` via
   `svc.approval_count(r.id)`. (Mirror `platform_api.list_approvals`.)
2. `GET /approvals/{request_id}` — return `ApprovalRequestDetailOut`, enriching
   `current_approvals` + `actions` via `svc.approval_count` / `svc.list_actions`.
   (Mirror `platform_api.get_approval`.)

`ApprovalRequestDetailOut`, `ApprovalActionOut`, `approval_count()`, and
`list_actions()` already exist (shipped for SP17). Both endpoints stay on
`CurrentTenantUser`. The approve/reject/cancel POST endpoints are unchanged.

**Self-approval** is rejected by `ApprovalService.approve()` (maker == checker
→ `ValueError` → 400). The UI hides Approve/Reject and shows Cancel when the
current user is the requester, mirroring SP17.

## Frontend facts (near-pure client)

- api-client `resources.makerChecker.{listTenant, getTenant, approveTenant,
  rejectTenant, cancelTenant}` all exist (cast `{ data?, error? }`).
- queryKeys `approvals.tenant(filters)` + `approvals.detail(id)` exist.
- `@sacco/schemas/approvals.ts` has `ApprovalRequestOut`,
  `ApprovalRequestDetailOut`, `ApprovalActionOut`, `approveActionSchema`,
  `rejectActionSchema`, `operationLabel()`, and `PLATFORM_OPERATION_LABELS`.
- `StatusBadge` entity `approval_request`
  (pending/approved/rejected/cancelled/expired) already exists.
- Server-fetch via `getTenantPageContext()`; in-memory `<DataTable>` (the list
  endpoint is unpaginated, like every prior tenant module).
- Requester is a tenant_user (staff). There is **no** tenant-context endpoint to
  resolve a tenant_user UUID → name, so the inbox shows the requester id with a
  **"(you)"** marker when it matches the current user. (Platform resolved names
  via `admin.listUsers`; no tenant equivalent exists.)

## Screens

All under `app/(tenant-authed)/approvals/*`, gated by tenant auth only.

1. **`/approvals`** — inbox. `<ApprovalsTable>` (in-memory `<DataTable>`):
   columns Operation (`operationLabel`), Status (`<StatusBadge>`), Approvals
   ("X of N" from current_approvals/required_approvals), Requested
   (`<RelativeTime>`), row links to detail. Default filter `status=pending` via
   a status `filterSlot`. Empty state "No approval requests".
2. **`/approvals/my-submissions`** — same table, filtered to
   `requested_by=<currentUser.id>` (the operator's own requests, where they must
   wait for another approver). Reachable from a header link on the inbox.
3. **`/approvals/[id]`** — detail:
   - Header: operation label + `<StatusBadge>` + "X of N approved".
   - `<PayloadView>` — generic key/value tree of the operation payload.
   - Actions trail — list of `actions` (action / actor id / `<FormattedDateTime>`
     / comment).
   - `<ApprovalActions>` (client) — when `status === "pending"`:
     - requester ≠ current user → **Approve** (optional comment) + **Reject**
       (reason ≥ 10 chars), both in a form `<Dialog>` (NOT
       `<MakerCheckerConfirmDialog>` — this is the checker side; that locked copy
       is maker-side only).
     - requester === current user → a "You requested this" notice + **Cancel**
       (base `<ConfirmDialog destructive>`).
   - On success: toast + `router.refresh()`.

The tenant sidebar already links `/approvals` (the dead link 3g-2 fills).

## Operation labels

`operationLabel()` only checks `PLATFORM_OPERATION_LABELS` today. Add
`TENANT_OPERATION_LABELS` (the 8 rows above) and make `operationLabel()` consult
both maps (operation namespaces don't collide: platform uses
billing./tenant./platform_user./platform.; tenant uses
credit./ledger./members./savings./shares.). Unknown operations still fall back to
the humanized last dot-segment.

## Out of scope (deferred)

- Requester name resolution (no tenant endpoint → show id + "(you)").
- Server-side pagination (in-memory like every prior tenant module).
- `<AuditBar>` (tenant-schema records; covered by 3g-3 `/audit`).
- A "quorum reached / executed" callout beyond the status badge + execution_result
  raw view.

## Testing strategy

- **Backend** (`tests/modules/maker_checker/` — real Postgres, `sacco/sacco@localhost:5433/sacco_test`):
  - `GET /approvals` enriches `current_approvals` (submit a quorum-2 request,
    one approval, assert list row shows `current_approvals == 1`) and filters by
    `requested_by`.
  - `GET /approvals/{id}` returns `actions` trail + `current_approvals`.
- **@sacco/schemas:** `operationLabel()` returns the tenant labels for the 8
  operations and still humanizes an unknown key.
- **@sacco/portal:** Vitest + Testing Library —
  - `ApprovalsTable` (row link + "X of N" + empty).
  - `ApprovalActions` (pending non-self → Approve+Reject; self → Cancel + notice;
    reject reason < 10 chars blocks submit; valid approve calls `approveTenant`).
  - `PayloadView` (renders nested keys).
- Per-package `test` + `typecheck` + `lint` green.
