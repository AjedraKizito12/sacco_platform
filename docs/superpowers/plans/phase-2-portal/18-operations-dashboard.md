# Operations Dashboard (SP18) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Environment note (2026-06-20):** background subagents in this harness cannot obtain Edit-permission approval (they stall at the first edit), so SP17 was executed **inline** via executing-plans. Expect the same here.

**Goal:** Build the platform Operations Dashboard at `/platform/operations` — headline stat tiles + status breakdowns + outstanding-invoices summary — as a pure client of the existing `GET /platform/admin/dashboard-stats` aggregate endpoint.

**Architecture:** Server component fetches once via `getPlatformPageContext()`, gated `operations.read` (admin). Two single-use presentational components (`StatCard`, `StatusBreakdown`) render the metrics; a tiny `RefreshButton` client component calls `router.refresh()`. The hand-written `DashboardStatsOut` type lands in `@sacco/schemas`. No charts (no chart primitives exist). Zero backend changes.

**Tech Stack:** Next.js 15 App Router, React 19, TS strict, `@sacco/ui` (Card, StatusBadge, Money, Count, RelativeTime), `@sacco/schemas` (new Out type), `@sacco/api-client` (`resources.admin.dashboardStats`), Vitest + Testing Library.

---

## Contract & scope notes (read before starting)

- **Zero new backend endpoints** (contract B); everything under `admin/` (contract N). `resources.admin.dashboardStats()` + `queryKeys.admin.dashboardStats()` already exist. The endpoint is gated `CurrentAdmin`.
- **The `Promise<never>` cast wart applies** — cast `dashboardStats()` to `{ data?, error? }` with the standard comment (see SP15/16/17).
- **Backend facts (authoritative):** `GET /platform/admin/dashboard-stats` → `DashboardStatsOut`:
  - `tenants: dict[str,int]`, `subscriptions: dict[str,int]` — counts by status.
  - `mrr: dict[str,Decimal]`, `invoices_amount_outstanding: dict[str,Decimal]` — **`Decimal` serialises as JSON string**, so model as `Record<string, string>` (same as `Money`'s `amount` prop).
  - `invoices_outstanding: dict[str,int]` — counts by status (issued/partial/overdue).
  - `approvals_pending: int`, `active_impersonations: int`, `last_updated: datetime` (ISO string over the wire).
  - The endpoint caches 60s in Redis and **forbids cache-bypass params** — do NOT add a force-refresh query; `router.refresh()` re-runs the server fetch and gets the cache within the window.
- **Permission:** add `"operations.read": "admin"` to `permissions.ts`. Gate the page with `requirePlatformPermission(user, "operations.read")` and the sidebar link with `<PermissionGuard permission="operations.read">`. UI gating is UX-only; the API enforces (contract D).
- **Money & counts (contracts H/R):** amounts via `<Money amount currency />`, integers via `<Count value />`. No raw `toLocaleString`.
- **Verified component props:** `<Count value={number} />`; `<RelativeTime value={string|Date} />` (exported from the FormattedDate module, re-exported by `@sacco/ui`); `<Money amount={string} currency={string} />`; `<StatusBadge entity="tenant"|"subscription" status={string} />`; `<Card className />`. There is **no** `StatCard` in `@sacco/ui` — it's single-use, lives beside the page.
- **Out of scope:** charts (no primitives — defer); active-impersonations drill-down (no list screen); auto-refresh; settings/audit (other nav groups); e2e + next-intl (portal-wide deferrals).

## File Structure

**`@sacco/schemas`**
- Modify `packages/schemas/src/platform.ts` — add `DashboardStatsOut` interface.

**`@sacco/portal`**
- Modify `apps/portal/src/auth/permissions.ts` — add `"operations.read": "admin"`.
- Create `app/platform/(authed)/operations/_components/StatCard.tsx`.
- Create `app/platform/(authed)/operations/_components/StatusBreakdown.tsx`.
- Create `app/platform/(authed)/operations/_components/RefreshButton.tsx`.
- Create `app/platform/(authed)/operations/page.tsx`.
- Modify `apps/portal/src/components/AppShellSidebar.tsx` — add the gated "Operations" platform nav link (between Audit and Settings) + import its icon.

**Tests** under `apps/portal/src/__tests__/platform-operations/`.

---

## Task 1: `DashboardStatsOut` type + `operations.read` permission

**Files:**
- Modify: `admin/packages/schemas/src/platform.ts`
- Modify: `admin/apps/portal/src/auth/permissions.ts`

- [ ] **Step 1: Add the Out type to `platform.ts`**

Append (after the existing `PlatformUserOut` block, mirroring the hand-written style):

```ts
// Mirrors app/platform_/admin/schemas.py DashboardStatsOut. Decimal fields
// arrive as JSON strings (FastAPI serialises Decimal as a string), so the
// per-currency maps are Record<string, string> — the same shape <Money> reads.
export interface DashboardStatsOut {
  tenants: Record<string, number>;
  subscriptions: Record<string, number>;
  mrr: Record<string, string>;
  invoices_outstanding: Record<string, number>;
  invoices_amount_outstanding: Record<string, string>;
  approvals_pending: number;
  active_impersonations: number;
  last_updated: string;
}
```

- [ ] **Step 2: Add the permission key to `permissions.ts`**

Insert after the Audit block (the `"audit.read": "admin",` line):

```ts
  // Operations
  "operations.read": "admin",
```

- [ ] **Step 3: Typecheck both packages**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/portal typecheck`
Expected: clean (no test yet — these are a type + a record entry; covered indirectly by later tasks and the full suite).

- [ ] **Step 4: Commit**

```bash
cd /home/liam/projects/sacco-platform
git add admin/packages/schemas/src/platform.ts admin/apps/portal/src/auth/permissions.ts
git commit -m "feat(portal): DashboardStatsOut type + operations.read permission

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `StatCard` component

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/operations/_components/StatCard.tsx`
- Test: `admin/apps/portal/src/__tests__/platform-operations/StatCard.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatCard } from "../../../app/platform/(authed)/operations/_components/StatCard";

describe("StatCard", () => {
  it("renders label, value, and sub", () => {
    render(<StatCard label="Tenants" value={<span>42</span>} sub={<span>38 active</span>} />);
    expect(screen.getByText("Tenants")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("38 active")).toBeInTheDocument();
  });

  it("renders as a link when href is set", () => {
    render(<StatCard label="Pending approvals" value={<span>3</span>} href="/platform/approvals?status=pending" />);
    const link = screen.getByRole("link", { name: /pending approvals/i });
    expect(link).toHaveAttribute("href", "/platform/approvals?status=pending");
  });

  it("is not a link when href is omitted", () => {
    render(<StatCard label="Active impersonations" value={<span>1</span>} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/portal test -- StatCard`
Expected: FAIL — component does not exist.

- [ ] **Step 3: Implement `StatCard.tsx`**

```tsx
import type { ReactNode } from "react";
import Link from "next/link";
import { Card } from "@sacco/ui";

export interface StatCardProps {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  href?: string;
}

export function StatCard({ label, value, sub, href }: StatCardProps) {
  const body = (
    <Card className="flex flex-col gap-1 p-5">
      <span className="text-[13px] text-[var(--text-tertiary)]">{label}</span>
      <span className="text-[var(--text-h3)] font-semibold text-[var(--text-primary)]">
        {value}
      </span>
      {sub ? <span className="text-[13px] text-[var(--text-secondary)]">{sub}</span> : null}
    </Card>
  );
  if (href) {
    return (
      <Link
        href={href}
        aria-label={label}
        className="block rounded-[var(--radius-md)] transition-colors hover:bg-[var(--surface-hover)]"
      >
        {body}
      </Link>
    );
  }
  return body;
}
```

> If `--radius-md` isn't a real token, drop the class (grep `rg "radius-" admin/packages/ui/src/tokens.css`). The link must expose an accessible name equal to `label` (the test queries by it).

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/portal test -- StatCard`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/liam/projects/sacco-platform
git add "admin/apps/portal/app/platform/(authed)/operations/_components/StatCard.tsx" admin/apps/portal/src/__tests__/platform-operations/StatCard.test.tsx
git commit -m "feat(portal): operations StatCard tile

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `StatusBreakdown` component

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/operations/_components/StatusBreakdown.tsx`
- Test: `admin/apps/portal/src/__tests__/platform-operations/StatusBreakdown.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBreakdown } from "../../../app/platform/(authed)/operations/_components/StatusBreakdown";

describe("StatusBreakdown", () => {
  it("renders a row per status with its count", () => {
    render(
      <StatusBreakdown
        title="Tenants by status"
        entity="tenant"
        counts={{ active: 38, suspended: 3, provisioning: 1 }}
      />,
    );
    expect(screen.getByText("Tenants by status")).toBeInTheDocument();
    expect(screen.getByText("38")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("orders rows by count descending", () => {
    render(
      <StatusBreakdown
        title="Subscriptions by status"
        entity="subscription"
        counts={{ trialing: 4, active: 35, past_due: 2 }}
      />,
    );
    const counts = screen.getAllByTestId("breakdown-count").map((n) => n.textContent);
    expect(counts).toEqual(["35", "4", "2"]);
  });

  it("shows an empty hint when there are no entries", () => {
    render(<StatusBreakdown title="Tenants by status" entity="tenant" counts={{}} />);
    expect(screen.getByText("No data")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/portal test -- StatusBreakdown`
Expected: FAIL — component does not exist.

- [ ] **Step 3: Implement `StatusBreakdown.tsx`**

```tsx
import { Card, Count, StatusBadge } from "@sacco/ui";

export interface StatusBreakdownProps {
  title: string;
  entity: "tenant" | "subscription";
  counts: Record<string, number>;
}

export function StatusBreakdown({ title, entity, counts }: StatusBreakdownProps) {
  const rows = Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));

  return (
    <Card className="flex flex-col gap-2 p-5">
      <h2 className="text-[var(--text-h5)] font-semibold">{title}</h2>
      {rows.length === 0 ? (
        <p className="text-[var(--text-tertiary)]">No data</p>
      ) : (
        <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
          {rows.map(([status, count]) => (
            <div key={status} className="flex items-center justify-between py-2">
              <StatusBadge entity={entity} status={status} />
              <Count value={count} data-testid="breakdown-count" />
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
```

> `Count` forwards extra props to its `<span>` (it spreads `...props`), so `data-testid` lands on the rendered element.

- [ ] **Step 4: Run to verify it passes**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/portal test -- StatusBreakdown`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/liam/projects/sacco-platform
git add "admin/apps/portal/app/platform/(authed)/operations/_components/StatusBreakdown.tsx" admin/apps/portal/src/__tests__/platform-operations/StatusBreakdown.test.tsx
git commit -m "feat(portal): operations StatusBreakdown card

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `RefreshButton` + Operations page + sidebar link

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/operations/_components/RefreshButton.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/operations/page.tsx`
- Modify: `admin/apps/portal/src/components/AppShellSidebar.tsx`

> The page is a server component doing a real fetch — not unit-tested in isolation (consistent with SP16/17 list/detail pages); the component tests + typecheck/lint/full-suite are the gate.

- [ ] **Step 1: Implement `RefreshButton.tsx`**

```tsx
"use client";

import { useRouter } from "next/navigation";
import { Button } from "@sacco/ui";

export function RefreshButton() {
  const router = useRouter();
  return (
    <Button variant="secondary" onClick={() => router.refresh()}>
      Refresh
    </Button>
  );
}
```

- [ ] **Step 2: Implement `page.tsx`**

```tsx
import type { ReactNode } from "react";
import { Card, Count, Money, RelativeTime } from "@sacco/ui";
import type { DashboardStatsOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { StatCard } from "./_components/StatCard";
import { StatusBreakdown } from "./_components/StatusBreakdown";
import { RefreshButton } from "./_components/RefreshButton";

export const metadata = { title: "Operations" };

function sumValues(d: Record<string, number>): number {
  return Object.values(d).reduce((a, b) => a + b, 0);
}

function MoneyList({ amounts }: { amounts: Record<string, string> }): ReactNode {
  const entries = Object.entries(amounts);
  if (entries.length === 0) return <>—</>;
  return (
    <span className="flex flex-col">
      {entries.map(([currency, amount], i) => (
        <Money
          key={currency}
          amount={amount}
          currency={currency}
          className={i === 0 ? "" : "text-[13px] text-[var(--text-secondary)]"}
        />
      ))}
    </span>
  );
}

export default async function OperationsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "operations.read");

  const { data } = await (
    resources.admin.dashboardStats() as Promise<{
      data?: DashboardStatsOut;
      error?: unknown;
    }>
  );

  if (!data) {
    return (
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-[var(--text-h3)] font-semibold">Operations</h1>
          <RefreshButton />
        </div>
        <Card className="p-6 text-[var(--text-secondary)]">
          Couldn&apos;t load operations stats. Please try again.
        </Card>
      </div>
    );
  }

  const outstandingEntries = Object.entries(data.invoices_outstanding);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Operations</h1>
        <div className="flex items-center gap-3">
          <span className="text-[13px] text-[var(--text-tertiary)]">
            Last updated <RelativeTime value={data.last_updated} />
          </span>
          <RefreshButton />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Tenants"
          value={<Count value={sumValues(data.tenants)} />}
          sub={<><Count value={data.tenants["active"] ?? 0} /> active</>}
        />
        <StatCard label="MRR" value={<MoneyList amounts={data.mrr} />} />
        <StatCard
          label="Pending approvals"
          value={<Count value={data.approvals_pending} />}
          href="/platform/approvals?status=pending"
        />
        <StatCard
          label="Active impersonations"
          value={<Count value={data.active_impersonations} />}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <StatusBreakdown title="Tenants by status" entity="tenant" counts={data.tenants} />
        <StatusBreakdown
          title="Subscriptions by status"
          entity="subscription"
          counts={data.subscriptions}
        />
      </div>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Outstanding invoices</h2>
        {outstandingEntries.length === 0 ? (
          <p className="text-[var(--text-tertiary)]">No outstanding invoices</p>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {outstandingEntries.map(([status, count]) => (
                <span key={status} className="text-[var(--text-secondary)]">
                  {status} <Count value={count} className="text-[var(--text-primary)]" />
                </span>
              ))}
            </div>
            <MoneyList amounts={data.invoices_amount_outstanding} />
          </div>
        )}
        <a
          href="/platform/billing/invoices"
          className="self-start text-[13px] text-[var(--text-link)] hover:underline"
        >
          View invoices
        </a>
      </Card>
    </div>
  );
}
```

> Verify `--text-link` / `--border-subtle` / `--surface-hover` tokens exist (they're used elsewhere in the portal — they do). `Money`'s `className` prop: confirm it forwards (it does — `Money` spreads props to its span). If `MoneyList`'s `className` on `<Money>` isn't supported, wrap each in a styled span instead.

- [ ] **Step 3: Add the gated sidebar link (AppShellSidebar.tsx)**

In the **platform** branch, add an "Operations" item between the Audit `<PermissionGuard>` block and the Settings `<SidebarItem>`. Import an icon (e.g. `Activity`) from `lucide-react` (add to the existing import list; `LayoutGrid` is taken by Dashboard).

```tsx
                <PermissionGuard permission="operations.read">
                  <SidebarItem
                    href="/platform/operations"
                    icon={<Activity size={ICON_SIZE} strokeWidth={1.75} />}
                    label="Operations"
                    active={isActive("/platform/operations")}
                  />
                </PermissionGuard>
```

Add `Activity` to the `lucide-react` import.

- [ ] **Step 4: Typecheck + lint**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
cd /home/liam/projects/sacco-platform
git add "admin/apps/portal/app/platform/(authed)/operations/_components/RefreshButton.tsx" "admin/apps/portal/app/platform/(authed)/operations/page.tsx" admin/apps/portal/src/components/AppShellSidebar.tsx
git commit -m "feat(portal): operations dashboard page + sidebar link

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Full verification + PR

**Files:** none (verification only).

- [ ] **Step 1: Portal per-package gate**

Run:
```bash
cd /home/liam/projects/sacco-platform/admin
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Expected: all PASS / clean. Record the portal test count (it should rise by the StatCard + StatusBreakdown cases over the SP17 baseline of 159).

- [ ] **Step 2: Contract spot-check**

- [ ] Every changed path is under `admin/` (`git diff --name-only main... | grep -v '^admin/' | grep -v '^docs/'` returns nothing).
- [ ] No new backend endpoint, no backend file touched (`git diff --name-only main... | grep -E '^app/|^tests/'` returns nothing for this sub-plan's commits).
- [ ] No raw `toLocaleString` in the operations tree (`rg "toLocaleString" "admin/apps/portal/app/platform/(authed)/operations"` returns nothing).

- [ ] **Step 3: Final holistic review**

Confirm: admin gating on page + sidebar; MRR/invoice amounts via `<Money>`, counts via `<Count>`; "Last updated" via `<RelativeTime>`; Pending-approvals tile links to the filtered inbox; error state renders without `notFound()`; no charts; no cache-bypass param.

- [ ] **Step 4: Open the PR**

```bash
cd /home/liam/projects/sacco-platform
git push -u origin <branch>
gh pr create --title "feat(portal): operations dashboard (SP18)" --body "$(cat <<'EOF'
## Summary
- New `/platform/operations` dashboard: headline stat tiles (tenants, MRR, pending approvals, active impersonations) + tenant/subscription status breakdowns + outstanding-invoices summary.
- Pure client of the existing `GET /platform/admin/dashboard-stats` (admin-gated); zero backend changes.
- `operations.read` permission (admin) gates the page and the new sidebar link. "Last updated" via `<RelativeTime>` + manual Refresh (the endpoint caches 60s and forbids cache-bypass, so no polling).

## Test plan
- `@sacco/schemas` + `@sacco/portal` test/typecheck/lint green; StatCard + StatusBreakdown unit tests.
- All changes under `admin/` (contracts B/N).

> CI note: the Lint check fails environmentally on this repo (account billing lock, not code); reproduce locally. Not a required check.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

> Decide the branch name with the established convention: `feat/portal-v1/18-operations-dashboard` (branch off `main` if SP17's branch has merged; otherwise the controller decides whether to stack on SP17 or branch fresh).

---

## Self-review notes (author)

- **Spec coverage:** `DashboardStatsOut` + permission → Task 1. StatCard → Task 2. StatusBreakdown → Task 3. Page (tiles + breakdowns + outstanding-invoices + error/empty states + Last-updated + Refresh) + sidebar link → Task 4. Verification + PR → Task 5. Decisions: admin gating (Task 1 + Task 4 page/sidebar), static+refresh (RefreshButton + RelativeTime, no polling/force-refresh).
- **Type consistency:** `DashboardStatsOut` field names/types in Task 1 match every consumption in Task 4 (`tenants`, `subscriptions`, `mrr`, `invoices_outstanding`, `invoices_amount_outstanding`, `approvals_pending`, `active_impersonations`, `last_updated`). `StatCardProps` (Task 2) and `StatusBreakdownProps` (Task 3) match their Task-4 call sites. `entity` union `"tenant"|"subscription"` matches the StatusBadge entities used.
- **Things to verify during execution (grep commands inline):** `--radius-md` / `--surface-hover` / `--text-link` tokens; `Money`/`Count` className forwarding; lucide `Activity` icon name.
