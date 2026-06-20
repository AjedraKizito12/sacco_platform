# Portal — MakerCheckerBanner Wiring (SP21) Design

**Date:** 2026-06-20
**Phase:** 2 (Admin Portal), sub-plan 21
**Status:** Approved

## Goal

Light up the `@sacco/ui` `<MakerCheckerBanner>` on the four platform detail
pages whose records can have an open maker-checker request (invoice,
subscription, tenant, platform user), closing the deferral notes left in
SP14/SP15/SP16. The banner tells an operator "this record has a pending
approval" with quorum and a link to review it.

## Contract posture (pure client — zero new endpoints)

The SP14/15/16 TODOs assumed new backend `pending_approval_request_id` fields.
**SP19 made that unnecessary:** the existing `GET /platform/approvals` list
endpoint already returns each request's `payload`, `current_approvals`,
`required_approvals`, `requested_by`, `requested_at`, and `operation_type`. A
detail page can therefore find its own open approval entirely client-side. SP21
is a **pure client** (contracts B/N) — no backend files change; all work under
`admin/`.

Already in place (verified):

- **@sacco/ui:** `<MakerCheckerBanner>` (presentational) with props
  `approvalRequestId, operationLabel, requesterName, requestedAt (string |
  ReactNode), quorumRequired, quorumCurrent, action (ReactNode), className?`.
- **api-client:** `resources.makerChecker.listPlatform(query)` (accepts
  `?status=`), `resources.admin.listUsers()`.
- **@sacco/schemas:** `ApprovalRequestOut` with `id, operation_type, payload,
  requested_by, requested_at, required_approvals, current_approvals, status,
  …`; `operationLabel()` + `PLATFORM_OPERATION_LABELS`.
- **server helper:** `getPlatformPageContext()` (React-`cache()`'d — a second
  call inside a page render reuses the request's auth resolution).
- The four detail pages already render `<AuditBarConnected>` (SP19), so the
  server-component wiring pattern is established.

## Backend facts (authoritative — payload keys)

Submit-time payloads (confirmed in `app/platform_/`):

| Operation | Payload key referencing the record |
|-----------|------------------------------------|
| `billing.void_invoice` | `invoice_id` |
| `billing.cancel_subscription` | `subscription_id` |
| `tenant.suspend` | `tenant_id` |
| `tenant.retry_provisioning` | `tenant_id` |
| `platform_user.update_sensitive` | `user_id` |

The list endpoint filters by `status`/`operation_type`/`requested_by` only — it
does **not** filter by payload contents — so the match on the record id happens
client-side after fetching pending requests.

## Architecture

### `src/lib/approval-subjects.ts`

The entity → operation/payload-key map and the matcher:

```ts
export interface ApprovalSubjectRule { operationType: string; payloadKey: string; }

export const APPROVAL_SUBJECTS: Record<string, ApprovalSubjectRule[]> = {
  invoice: [{ operationType: "billing.void_invoice", payloadKey: "invoice_id" }],
  subscription: [{ operationType: "billing.cancel_subscription", payloadKey: "subscription_id" }],
  tenant: [
    { operationType: "tenant.suspend", payloadKey: "tenant_id" },
    { operationType: "tenant.retry_provisioning", payloadKey: "tenant_id" },
  ],
  platform_user: [{ operationType: "platform_user.update_sensitive", payloadKey: "user_id" }],
};

// Given pending ApprovalRequestOut[], return the first whose operation_type +
// payload[payloadKey] match this entity/record. Pure function, unit-tested.
export function findOpenApproval(
  entityType: string,
  recordId: string,
  pending: ApprovalRequestOut[],
): ApprovalRequestOut | null;
```

`findOpenApproval` only considers requests with `status === "pending"` (the
fetch already filters, but the helper double-checks so it's safe in isolation)
and an operation_type in the entity's rule set whose `payload[payloadKey] ===
recordId`. Returns the first match (there is at most one open mutation approval
per record in practice).

### `src/components/MakerCheckerBannerConnected.tsx` (server component)

Sibling to `AuditBarConnected`:

1. If `entityType` has no rules → render nothing (`return null`).
2. `getPlatformPageContext()` → `resources.makerChecker.listPlatform({ status:
   "pending" })` (cast `{ data?, error? }`). On error/undefined → `null`.
3. `const open = findOpenApproval(entityType, entityId, data ?? [])`. If `null`
   → render nothing.
4. Resolve the requester name via `admin.listUsers()` (Map<id, label>, same as
   the approvals inbox; fall back to the raw id).
5. Render:

```tsx
<MakerCheckerBanner
  approvalRequestId={open.id}
  operationLabel={operationLabel(open.operation_type)}
  requesterName={requesterLabel}
  requestedAt={<FormattedDateTime value={open.requested_at} />}
  quorumRequired={open.required_approvals}
  quorumCurrent={open.current_approvals}
  action={
    <a href={`/platform/approvals/${open.id}`} className="text-[13px] underline">
      Review
    </a>
  }
/>
```

Rendering nothing when there is no open approval keeps every detail page's
normal state unchanged.

### Wiring the four detail pages

Render `<MakerCheckerBannerConnected entityType=… entityId={data.id} />` at the
**top of the record body** (above the first `<Card>`), on:

- `billing/invoices/[id]/page.tsx` — `entityType="invoice"` (server component → inline).
- `billing/subscriptions/[id]/page.tsx` — `entityType="subscription"` (server → inline).
- `tenants/[id]/page.tsx` — `entityType="tenant"`. `TenantDetail` is a **client**
  component, so pass the banner as a slot prop (`makerCheckerBanner: ReactNode`,
  the SP19 pattern) rendered at the top of the body.
- `users/[id]/page.tsx` — `entityType="platform_user"`. `UserDetail` already
  takes slot props (`auditBar`); add a `makerCheckerBanner` slot rendered above
  the identity card.

Because `<MakerCheckerBannerConnected>` and `<AuditBarConnected>` both call
`getPlatformPageContext()`, and that helper is React-`cache()`'d, the two extra
fetches share one auth resolution per request.

## Deliberate exclusions (documented, not gaps)

- **`billing.confirm_payment`** (keyed by `payment_id`, not `invoice_id`) — a
  pending recorded payment is already visible on the invoice's payment rows and
  in the Payments confirmation queue; the invoice banner does not duplicate it.
- **`platform.start_impersonation`** (references `tenant_id`) — it is a pending
  impersonation *request*, not a mutation of the tenant record, so it does not
  raise the tenant's "pending approval" banner.
- **Tenant-portal (tenant-scoped) maker-checker banners** — separate later
  work; SP21 is platform detail pages only.

## File structure

**`@sacco/portal`**
- Create `apps/portal/src/lib/approval-subjects.ts` + matcher.
- Create `apps/portal/src/components/MakerCheckerBannerConnected.tsx`.
- Modify `billing/invoices/[id]/page.tsx`, `billing/subscriptions/[id]/page.tsx`
  (inline banner) and remove the stale TODO in
  `billing/subscriptions/[id]/_components/SubscriptionActions.tsx`.
- Modify `tenants/[id]/page.tsx` + `_components/TenantDetail.tsx` (slot).
- Modify `users/[id]/page.tsx` + `_components/UserDetail.tsx` (slot).
- Tests under `apps/portal/src/__tests__/platform-maker-checker/`.

## Permission / gating

No new permission. The banner is read-only UX; the approvals it links to are
gated by `approvals.read` on the inbox (the link target). A user who can view a
detail page can see whether it has a pending approval — this is informational
and matches the existing detail-page read gate.

## Testing strategy

- **Portal:** Vitest + Testing Library.
  - `findOpenApproval` (pure unit): matches by operation_type + payload key;
    ignores non-pending; ignores wrong record id; returns null when none;
    tenant's two operation rules both match on `tenant_id`.
  - `MakerCheckerBannerConnected` is a server component (fetches) — not unit
    tested in isolation (consistent with `AuditBarConnected`); the matcher unit
    test + the existing `<MakerCheckerBanner>` component test cover the logic and
    render. The 4 page wirings are verified by typecheck/lint + the suite.
- Per-package `test` + `typecheck` + `lint` green; all changes under `admin/`.

## Out of scope (deferred)

- Tenant-portal maker-checker banners.
- Real-time / push updates (the banner reflects the server-render snapshot).
- Surfacing confirm_payment on the invoice banner (payment-scoped, visible
  elsewhere).
- e2e + next-intl — portal-wide deferrals.
