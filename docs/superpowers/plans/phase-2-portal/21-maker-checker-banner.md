# MakerCheckerBanner Wiring (SP21) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Environment note (2026-06-20):** background subagents in this harness cannot obtain Edit-permission approval; SP17–SP20 ran **inline** via executing-plans. Expect the same. **Pure client** — no backend, no test DB. **Always confirm typecheck PASSES before committing** (an SP20 amend was needed when a pre-Read edit had silently failed).

**Goal:** Render `<MakerCheckerBanner>` on the four platform detail pages (invoice, subscription, tenant, platform user) when the record has an open maker-checker request — closing the SP14/15/16 deferrals — entirely client-side using SP19's `/platform/approvals` list.

**Architecture:** A pure `findOpenApproval` matcher (entity → operation/payload-key map) + a server-component `<MakerCheckerBannerConnected>` (sibling to `AuditBarConnected`) that fetches pending approvals, matches this record, resolves the requester name, and renders the banner — or nothing. Wired inline on the two server-component detail pages and via a slot prop on the two client detail bodies. Zero backend.

**Tech Stack:** Next.js 15 App Router, React 19, TS strict, `@sacco/ui` (MakerCheckerBanner, FormattedDateTime), `@sacco/schemas` (`ApprovalRequestOut`, `operationLabel`), `@sacco/api-client` (`makerChecker.listPlatform`, `admin.listUsers`), Vitest + Testing Library.

---

## Contract & scope notes (read before starting)

- **Zero new endpoints** (contract B); everything under `admin/` (contract N). Uses the existing `GET /platform/approvals?status=pending` (SP19) which returns `payload`, `current_approvals`, `required_approvals`, `requested_by`, `requested_at`, `operation_type`, `id`.
- **The `Promise<never>` cast** applies to `makerChecker.listPlatform` and `admin.listUsers` (cast to `{ data?, error? }`).
- **Payload keys (confirmed):** `billing.void_invoice → invoice_id`, `billing.cancel_subscription → subscription_id`, `tenant.suspend → tenant_id`, `tenant.retry_provisioning → tenant_id`, `platform_user.update_sensitive → user_id`.
- **Exclusions (documented):** `billing.confirm_payment` (payment-scoped, not invoice), `platform.start_impersonation` (request, not a tenant mutation), tenant-portal banners.
- **Slot vs inline:** invoice + subscription detail pages are server components (render the banner inline); `TenantDetail` + `UserDetail` are consumed by server pages but `UserDetail`/`TenantDetail` take slot props (`UserDetail` already has `auditBar: ReactNode`) — pass the banner as a `makerCheckerBanner` slot.

## File structure

**`@sacco/portal`**
- Create `apps/portal/src/lib/approval-subjects.ts`.
- Create `apps/portal/src/components/MakerCheckerBannerConnected.tsx`.
- Modify `app/platform/(authed)/billing/invoices/[id]/page.tsx`.
- Modify `app/platform/(authed)/billing/subscriptions/[id]/page.tsx`.
- Modify `app/platform/(authed)/billing/subscriptions/[id]/_components/SubscriptionActions.tsx` (remove stale TODO).
- Modify `app/platform/(authed)/tenants/[id]/page.tsx` + `_components/TenantDetail.tsx`.
- Modify `app/platform/(authed)/users/[id]/page.tsx` + `_components/UserDetail.tsx`.
- Tests under `apps/portal/src/__tests__/platform-maker-checker/`.

---

## Task 1: `approval-subjects.ts` — map + `findOpenApproval`

**Files:**
- Create: `admin/apps/portal/src/lib/approval-subjects.ts`
- Test: `admin/apps/portal/src/__tests__/platform-maker-checker/approval-subjects.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from "vitest";
import type { ApprovalRequestOut } from "@sacco/schemas";
import { findOpenApproval } from "../../../src/lib/approval-subjects";

function req(over: Partial<ApprovalRequestOut>): ApprovalRequestOut {
  return {
    id: "ar1", operation_type: "billing.void_invoice", payload: { invoice_id: "inv1" },
    requested_by: "u1", requested_at: "2026-06-20T10:00:00Z",
    required_approvals: 1, current_approvals: 0, status: "pending",
    expires_at: null, executed_at: null, execution_result: null, rejection_reason: null,
    ...over,
  };
}

describe("findOpenApproval", () => {
  it("matches an invoice void by invoice_id", () => {
    const r = req({});
    expect(findOpenApproval("invoice", "inv1", [r])?.id).toBe("ar1");
  });
  it("returns null when the record id does not match the payload", () => {
    expect(findOpenApproval("invoice", "other", [req({})])).toBeNull();
  });
  it("ignores non-pending requests", () => {
    expect(findOpenApproval("invoice", "inv1", [req({ status: "executed" })])).toBeNull();
  });
  it("matches both tenant operation rules on tenant_id", () => {
    const suspend = req({ id: "a", operation_type: "tenant.suspend", payload: { tenant_id: "t1" } });
    const retry = req({ id: "b", operation_type: "tenant.retry_provisioning", payload: { tenant_id: "t1" } });
    expect(findOpenApproval("tenant", "t1", [retry])?.id).toBe("b");
    expect(findOpenApproval("tenant", "t1", [suspend])?.id).toBe("a");
  });
  it("returns null for an entity with no rules", () => {
    expect(findOpenApproval("loan", "x", [req({})])).toBeNull();
  });
});
```

Run: `cd admin && pnpm --filter @sacco/portal test -- approval-subjects` → FAIL.

- [ ] **Step 2: Implement `approval-subjects.ts`**

```ts
import type { ApprovalRequestOut } from "@sacco/schemas";

export interface ApprovalSubjectRule {
  operationType: string;
  payloadKey: string;
}

export const APPROVAL_SUBJECTS: Record<string, ApprovalSubjectRule[]> = {
  invoice: [{ operationType: "billing.void_invoice", payloadKey: "invoice_id" }],
  subscription: [
    { operationType: "billing.cancel_subscription", payloadKey: "subscription_id" },
  ],
  tenant: [
    { operationType: "tenant.suspend", payloadKey: "tenant_id" },
    { operationType: "tenant.retry_provisioning", payloadKey: "tenant_id" },
  ],
  platform_user: [
    { operationType: "platform_user.update_sensitive", payloadKey: "user_id" },
  ],
};

/**
 * The first pending approval whose operation_type + payload reference this
 * record. Pure — the caller passes already-fetched requests.
 */
export function findOpenApproval(
  entityType: string,
  recordId: string,
  pending: ApprovalRequestOut[],
): ApprovalRequestOut | null {
  const rules = APPROVAL_SUBJECTS[entityType];
  if (!rules) return null;
  for (const r of pending) {
    if (r.status !== "pending") continue;
    const rule = rules.find((x) => x.operationType === r.operation_type);
    if (!rule) continue;
    if (r.payload[rule.payloadKey] === recordId) return r;
  }
  return null;
}
```

- [ ] **Step 3: Run → PASS; commit.**

```bash
cd /home/liam/projects/sacco-platform
git add admin/apps/portal/src/lib/approval-subjects.ts admin/apps/portal/src/__tests__/platform-maker-checker/approval-subjects.test.ts
git commit -m "feat(portal): approval-subjects map + findOpenApproval matcher

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `<MakerCheckerBannerConnected>` server component

**Files:**
- Create: `admin/apps/portal/src/components/MakerCheckerBannerConnected.tsx`

> Server component that fetches — not unit-tested in isolation (consistent with `AuditBarConnected`); the matcher unit test (T1) + the existing `<MakerCheckerBanner>` component test cover logic + render. Verified by typecheck/lint + the suite.

- [ ] **Step 1: Implement it**

```tsx
import { MakerCheckerBanner } from "@sacco/ui";
import { FormattedDateTime } from "@sacco/ui";
import type { ApprovalRequestOut, PlatformUserOut } from "@sacco/schemas";
import { operationLabel } from "@sacco/schemas";
import { getPlatformPageContext } from "@/auth/server-page-context";
import { APPROVAL_SUBJECTS, findOpenApproval } from "@/lib/approval-subjects";

export async function MakerCheckerBannerConnected({
  entityType,
  entityId,
}: {
  entityType: string;
  entityId: string;
}) {
  if (!APPROVAL_SUBJECTS[entityType]) return null;

  const { resources } = await getPlatformPageContext();
  const { data } = await (
    resources.makerChecker.listPlatform({ status: "pending" }) as Promise<{
      data?: ApprovalRequestOut[];
      error?: unknown;
    }>
  );
  const open = findOpenApproval(entityType, entityId, data ?? []);
  if (!open) return null;

  const { data: users } = await (
    resources.admin.listUsers() as Promise<{ data?: PlatformUserOut[]; error?: unknown }>
  );
  const requester = (users ?? []).find((u) => u.id === open.requested_by);
  const requesterName = requester
    ? requester.full_name || requester.email
    : open.requested_by;

  return (
    <MakerCheckerBanner
      approvalRequestId={open.id}
      operationLabel={operationLabel(open.operation_type)}
      requesterName={requesterName}
      requestedAt={<FormattedDateTime value={open.requested_at} />}
      quorumRequired={open.required_approvals}
      quorumCurrent={open.current_approvals}
      action={
        <a
          href={`/platform/approvals/${open.id}`}
          className="text-[13px] underline underline-offset-2"
        >
          Review
        </a>
      }
    />
  );
}
```

> Combine the two `@sacco/ui` imports into one line if lint prefers. `getPlatformPageContext()` is React-`cache()`'d, so this fetch shares auth with the page's other server fetches.

- [ ] **Step 2: Typecheck + lint; commit.**

```bash
cd admin && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
cd /home/liam/projects/sacco-platform
git add admin/apps/portal/src/components/MakerCheckerBannerConnected.tsx
git commit -m "feat(portal): MakerCheckerBannerConnected server wrapper

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Wire the four detail pages

**Files:**
- Modify: `billing/invoices/[id]/page.tsx`, `billing/subscriptions/[id]/page.tsx` (inline)
- Modify: `billing/subscriptions/[id]/_components/SubscriptionActions.tsx` (remove TODO)
- Modify: `tenants/[id]/page.tsx` + `_components/TenantDetail.tsx` (slot)
- Modify: `users/[id]/page.tsx` + `_components/UserDetail.tsx` (slot)

- [ ] **Step 1: Invoice page (inline)** — import `MakerCheckerBannerConnected`; render it as the first child of the returned `<div className="flex flex-col gap-6">`, before the header row:

```tsx
<MakerCheckerBannerConnected entityType="invoice" entityId={data.id} />
```

- [ ] **Step 2: Subscription page (inline)** — same, `entityType="subscription"`.

- [ ] **Step 3: Remove the stale TODO** in `SubscriptionActions.tsx` (the `// TODO: Contract K — when SubscriptionOut gains … render <MakerCheckerBanner> …` comment block). Read it first; delete only that comment.

- [ ] **Step 4: Tenant (slot)** — `TenantDetail` is `"use client"`. Add a `makerCheckerBanner: ReactNode` prop (alongside the existing props), render `{makerCheckerBanner}` as the first child of its root `<div>` (above the header row). In `tenants/[id]/page.tsx`, import `MakerCheckerBannerConnected` and pass `makerCheckerBanner={<MakerCheckerBannerConnected entityType="tenant" entityId={data.id} />}`. Update the `TenantDetail.test.tsx` `renderDetail` helper to pass `makerCheckerBanner={null}`.

- [ ] **Step 5: Platform user (slot)** — `UserDetail` already takes `auditBar: ReactNode`. Add `makerCheckerBanner: ReactNode`; render `{makerCheckerBanner}` as the first child of its root `<div>` (above the identity header). In `users/[id]/page.tsx`, pass `makerCheckerBanner={<MakerCheckerBannerConnected entityType="platform_user" entityId={data.id} />}`. Update `UserDetail.test.tsx`'s render calls to pass `makerCheckerBanner={null}` (or a placeholder).

- [ ] **Step 6: Typecheck + lint + the affected component tests.**

Run:
```bash
cd admin && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
pnpm --filter @sacco/portal test -- "TenantDetail|UserDetail"
```
Expected: clean + PASS.

- [ ] **Step 7: Commit**

```bash
cd /home/liam/projects/sacco-platform
git add "admin/apps/portal/app/platform/(authed)/"
git commit -m "feat(portal): render MakerCheckerBanner on invoice/subscription/tenant/user detail

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Verification + PR

- [ ] **Step 1: Portal gate**

```bash
cd /home/liam/projects/sacco-platform/admin
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Record the test count (rises by the `findOpenApproval` cases over SP20's 172).

- [ ] **Step 2: Contract spot-checks**

- [ ] All changes under `admin/` + `docs/` (`git diff --name-only main...HEAD | grep -vE '^(admin/|docs/)'` empty).
- [ ] No backend files (`git diff --name-only main...HEAD | grep -E '^(app/|tests/)'` empty).
- [ ] No new endpoint used beyond the existing `/platform/approvals` (grep the new files for `listPlatform`/`listUsers` only).

- [ ] **Step 3: Final holistic review** — confirm: banner renders only when an open approval matches; renders nothing otherwise (detail pages' normal state unchanged); quorum shows `current of required`; the "Review" link targets `/platform/approvals/{id}`; the stale SubscriptionActions TODO is gone; confirm_payment/impersonation correctly excluded.

- [ ] **Step 4: Push + PR**

```bash
cd /home/liam/projects/sacco-platform
git push -u origin feat/portal-v1/21-maker-checker-banner
gh pr create --title "feat(portal): MakerCheckerBanner on detail pages (SP21)" --body "$(cat <<'EOF'
## Summary
- Renders `<MakerCheckerBanner>` on the invoice / subscription / tenant / platform-user detail pages when the record has an open maker-checker request — closing the SP14/15/16 deferrals.
- **Pure client; zero backend.** Uses SP19's `/platform/approvals?status=pending` (which already returns `payload` + `current_approvals`), matched to the record id by a small entity→payload-key map. The originally-assumed `pending_approval_request_id` backend fields proved unnecessary.
- Banner renders nothing when there is no open approval — detail pages' normal state is unchanged.

## Notable points
- `findOpenApproval` (pure, unit-tested) matches operation_type + payload key per entity.
- Excludes `billing.confirm_payment` (payment-scoped) and `platform.start_impersonation` (a request, not a tenant mutation) — documented.
- `<MakerCheckerBannerConnected>` is a server component (sibling to `AuditBarConnected`); client detail bodies (TenantDetail/UserDetail) receive it as a slot.

## Test plan
- `@sacco/portal` test/typecheck/lint green (`findOpenApproval` cases; TenantDetail/UserDetail still pass with the new slot).
- All changes under `admin/` (contracts B/N); no backend files touched.

> CI note: Lint fails environmentally on this repo (account billing lock); reproduced clean locally. Not a required check.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (author)

- **Spec coverage:** map + matcher → T1; connected wrapper → T2; 4 page wirings + TODO removal → T3; verification/PR → T4.
- **Type consistency:** `ApprovalSubjectRule`/`APPROVAL_SUBJECTS`/`findOpenApproval` (T1) consumed by `MakerCheckerBannerConnected` (T2). Banner props match the `@sacco/ui` `MakerCheckerBannerProps` (approvalRequestId/operationLabel/requesterName/requestedAt/quorumRequired/quorumCurrent/action). `makerCheckerBanner: ReactNode` slot added to TenantDetail + UserDetail (T3) matches the page pass-down.
- **Verify-at-execution (grep inline):** the exact root-`<div>` opening in each page (insert banner as first child); the SubscriptionActions TODO comment text; that `UserDetail`/`TenantDetail` tests enumerate their render calls (update each to pass the new slot).
