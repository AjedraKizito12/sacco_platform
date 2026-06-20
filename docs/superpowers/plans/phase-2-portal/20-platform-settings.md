# Platform Settings (SP20) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Environment note (2026-06-20):** background subagents in this harness cannot obtain Edit-permission approval; SP17–SP19 ran **inline** via executing-plans. Expect the same. This sub-plan is **pure client** — no backend, no test DB needed.

**Goal:** Fill the Settings nav group as a read-only hub — index + Security (real JWT signing-key view) + Billing (informational) + Notifications (Phase-3 placeholder) — completing the 7-nav-group portal inventory.

**Architecture:** Pure client of the existing superuser-gated `GET /platform/jwt-keys`. New `settings.read` (admin) permission gates the hub/billing/notifications; the existing `platform.security.jwt_keys.read` (superuser) gates Security. A `jwt_key` StatusBadge entity, a `JwtKeyOut` schema, a `keys` api-client resource, and four pages + an in-memory `JwtKeysTable`. Zero backend changes.

**Tech Stack:** Next.js 15 App Router, React 19, TS strict, `@sacco/ui` (DataTable, StatusBadge, Card, FormattedDate), `@sacco/schemas`, `@sacco/api-client`, Vitest + Testing Library.

---

## Contract & scope notes (read before starting)

- **Zero new backend endpoints** (contract B); everything under `admin/` (contract N).
- **Backend facts:** `GET /platform/jwt-keys` → `list[JwtKeyOut]`, **superuser-gated** (`dependencies=[Depends(get_current_superuser)]` in `main.py`). `JwtKeyOut`: `id, kid, algorithm, audience, status, created_at, activated_at, retired_at, deleted_at`. `status ∈ {active, retiring, retired}`.
- **The `as never` / `Promise<never>` cast** applies to the new `keys` resource (written fresh, same convention as `makerChecker.ts`); cast results to `{ data?, error? }`.
- **Permissions:** add `settings.read → admin`; reuse `platform.security.jwt_keys.read → superuser` for Security. Gate the (currently ungated) sidebar Settings link with `settings.read`. UI gating is UX-only; the keys endpoint is the real superuser boundary (contract D).
- **Read-only:** no setting is editable (no backend store), no key rotation/create/delete actions (beat job + CLAUDE.md forbids direct key mutation).
- **Out of scope:** editing settings; key actions; real notifications (Phase 3); session-TTL/password-policy values (no endpoint); e2e + next-intl.

## File structure

**`@sacco/schemas`** — modify `src/platform.ts` (+ `JwtKeyOut`).
**`@sacco/api-client`** — create `src/resources/keys.ts`; modify `src/resources/index.ts`, `src/query-keys.ts`.
**`@sacco/ui`** — modify `src/components/StatusBadge/status-maps.ts` (+ `jwt_key`); maybe `StatusBadge.test.tsx`.
**`@sacco/portal`** — modify `src/auth/permissions.ts`, `src/components/AppShellSidebar.tsx`; create `app/platform/(authed)/settings/{page,billing/page,notifications/page,security/page}.tsx` + `security/_components/JwtKeysTable.tsx`; tests under `src/__tests__/platform-settings/`.

---

## Task 1: `JwtKeyOut` schema + `settings.read` permission

**Files:**
- Modify: `admin/packages/schemas/src/platform.ts`
- Modify: `admin/apps/portal/src/auth/permissions.ts`

- [ ] **Step 1: Add `JwtKeyOut` to `platform.ts`** (append after the existing Out types)

```ts
// Mirrors app/modules/iam/keys/schemas.py JwtKeyOut. Dates are ISO strings.
export interface JwtKeyOut {
  id: string;
  kid: string;
  algorithm: string;
  audience: string;
  status: string; // active | retiring | retired
  created_at: string;
  activated_at: string | null;
  retired_at: string | null;
  deleted_at: string | null;
}
```

- [ ] **Step 2: Add the permission** to `permissions.ts` (after the Operations block, before/near Audit — order doesn't matter functionally):

```ts
  // Settings
  "settings.read": "admin",
```

- [ ] **Step 3: Typecheck both packages**

Run: `cd /home/liam/projects/sacco-platform/admin && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/portal typecheck`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
cd /home/liam/projects/sacco-platform
git add admin/packages/schemas/src/platform.ts admin/apps/portal/src/auth/permissions.ts
git commit -m "feat(portal): JwtKeyOut type + settings.read permission

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `keys` api-client resource + queryKeys

**Files:**
- Create: `admin/packages/api-client/src/resources/keys.ts`
- Modify: `admin/packages/api-client/src/resources/index.ts`
- Modify: `admin/packages/api-client/src/query-keys.ts`

- [ ] **Step 1: Create `keys.ts`**

```ts
import type { FetchClient } from "../client";

export function keys(api: FetchClient) {
  return {
    listJwtKeys: () => api.GET("/platform/jwt-keys" as never, {} as never),
  } as const;
}
```

- [ ] **Step 2: Register in `resources/index.ts`** — import `keys` and add `keys: keys(api),` to the returned object, following the existing entries (e.g. how `audit` / `makerChecker` are registered — read the file and match the exact shape).

- [ ] **Step 3: Add `queryKeys.keys`** to `query-keys.ts` (after another domain block):

```ts
  keys: {
    root: () => ["keys"] as const,
    list: () => ["keys", "list"] as const,
  },
```

- [ ] **Step 4: Typecheck the package; commit.**

Run: `cd admin && pnpm --filter @sacco/api-client typecheck && pnpm --filter @sacco/api-client lint`

```bash
git add admin/packages/api-client/src/resources/keys.ts admin/packages/api-client/src/resources/index.ts admin/packages/api-client/src/query-keys.ts
git commit -m "feat(portal): keys api-client resource (listJwtKeys)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `jwt_key` StatusBadge entity (`@sacco/ui`)

**Files:**
- Modify: `admin/packages/ui/src/components/StatusBadge/status-maps.ts`
- Modify: `admin/packages/ui/src/components/StatusBadge/StatusBadge.test.tsx` (if it enumerates entities)

- [ ] **Step 1: Add to the `StatusEntity` union**

Add `| "jwt_key"` to the `StatusEntity` union (after `platform_user`).

- [ ] **Step 2: Add the map** (after `PLATFORM_USER_STATUS`)

```ts
export const JWT_KEY_STATUS: StatusMap = {
  active: { variant: "success", label: "Active" },
  retiring: { variant: "warning", label: "Retiring" },
  retired: { variant: "neutral", label: "Retired" },
};
```

- [ ] **Step 3: Register in `ENTITY_MAPS`** — add `jwt_key: JWT_KEY_STATUS,` to the `ENTITY_MAPS` record (TS enforces the union and the record stay in sync).

- [ ] **Step 4: Test**

Read `StatusBadge.test.tsx`. If it has a per-entity table/loop, add a `jwt_key` case asserting `active → "Active"` renders with the success variant. If it only tests generic behaviour, add a focused test:

```tsx
it("maps jwt_key statuses", () => {
  render(<StatusBadge entity="jwt_key" status="retiring" />);
  expect(screen.getByText("Retiring")).toBeInTheDocument();
});
```

- [ ] **Step 5: Run UI tests + typecheck + lint; commit.**

```bash
cd admin && pnpm --filter @sacco/ui test -- StatusBadge && pnpm --filter @sacco/ui typecheck && pnpm --filter @sacco/ui lint
cd /home/liam/projects/sacco-platform
git add admin/packages/ui/src/components/StatusBadge/
git commit -m "feat(ui): jwt_key StatusBadge entity

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `<JwtKeysTable>`

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/settings/security/_components/JwtKeysTable.tsx`
- Test: `admin/apps/portal/src/__tests__/platform-settings/JwtKeysTable.test.tsx`

- [ ] **Step 1: Failing test** (mock `useTableUrlState`, per the established DataTable test pattern — copy the mock block from `InvoicesTable.test.tsx`: `page/pageSize/sortColumn/sortDirection/filters/density` + all setters)

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@sacco/ui", async (importActual) => {
  const actual = await importActual<typeof import("@sacco/ui")>();
  return {
    ...actual,
    useTableUrlState: vi.fn().mockReturnValue({
      page: 1, pageSize: 25, sortColumn: null, sortDirection: "asc" as const,
      filters: {}, density: "default" as const,
      setPage: vi.fn(), setPageSize: vi.fn(), setSort: vi.fn(),
      setFilter: vi.fn(), setFilters: vi.fn(), setDensity: vi.fn(), reset: vi.fn(),
    }),
  };
});

import { JwtKeysTable } from "../../../app/platform/(authed)/settings/security/_components/JwtKeysTable";
import type { JwtKeyOut } from "@sacco/schemas";

const rows: JwtKeyOut[] = [{
  id: "k1", kid: "key-2026-06", algorithm: "RS256", audience: "platform",
  status: "active", created_at: "2026-06-01T00:00:00Z",
  activated_at: "2026-06-01T00:00:00Z", retired_at: null, deleted_at: null,
}];

describe("JwtKeysTable", () => {
  it("renders a key row with kid, status badge, and algorithm", () => {
    render(<JwtKeysTable rows={rows} />);
    expect(screen.getByText("key-2026-06")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("RS256")).toBeInTheDocument();
  });

  it("shows the empty state when there are no keys", () => {
    render(<JwtKeysTable rows={[]} />);
    expect(screen.getByText("No signing keys")).toBeInTheDocument();
  });
});
```

Run: `cd admin && pnpm --filter @sacco/portal test -- JwtKeysTable` → FAIL.

- [ ] **Step 2: Implement `JwtKeysTable.tsx`**

In-memory `<DataTable>` adapter (no filters needed — small list; sort optional). Mirror `InvoicesTable` structure minus the filter slot. Columns: kid (mono), status (`<StatusBadge entity="jwt_key">`), algorithm, audience, created (`<FormattedDate>`), activated (or "—"), retired (or "—"). `id = "settings-jwt-keys"`. `state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}`. `data={rows}` (in-memory; the list is tiny — paginate via the urlState slice like InvoicesTable, or just pass all rows since count is small — match InvoicesTable's slice pattern for consistency). `emptyState={{ title: "No signing keys", description: "Signing keys appear here once configured." }}`.

> Keep the in-memory filter/sort helpers minimal or omit (the list is a handful of rows). At minimum: `data={rows}` + `totalRows: rows.length`. To match contract T's server-side-mode wiring exactly, reuse the InvoicesTable slice (filter→sort→paginate) with no filter keys.

- [ ] **Step 3: Run → PASS.**

- [ ] **Step 4: Commit**

```bash
git add "admin/apps/portal/app/platform/(authed)/settings/security/_components/JwtKeysTable.tsx" admin/apps/portal/src/__tests__/platform-settings/JwtKeysTable.test.tsx
git commit -m "feat(portal): JwtKeysTable (read-only signing keys)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Settings pages + sidebar gating

**Files:**
- Create: `settings/page.tsx`, `settings/billing/page.tsx`, `settings/notifications/page.tsx`, `settings/security/page.tsx` (all under `app/platform/(authed)/`)
- Modify: `admin/apps/portal/src/components/AppShellSidebar.tsx`

- [ ] **Step 1: Hub `settings/page.tsx`** (server)

```tsx
import Link from "next/link";
import { Card } from "@sacco/ui";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";

export const metadata = { title: "Settings" };

function SettingCard({ href, title, desc }: { href: string; title: string; desc: string }) {
  return (
    <Link href={href} className="block">
      <Card className="flex flex-col gap-1 p-5 transition-colors hover:bg-[var(--surface-hover)]">
        <span className="text-[var(--text-h5)] font-semibold text-[var(--text-primary)]">{title}</span>
        <span className="text-[13px] text-[var(--text-secondary)]">{desc}</span>
      </Card>
    </Link>
  );
}

export default async function SettingsPage() {
  const { user } = await getPlatformPageContext();
  requirePlatformPermission(user, "settings.read");
  const canSecurity = userHasPermission(user, "platform.security.jwt_keys.read");

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Settings</h1>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <SettingCard href="/platform/settings/billing" title="Billing" desc="Invoice numbering, plans, and grace period." />
        <SettingCard href="/platform/settings/notifications" title="Notifications" desc="Email and SMS provider configuration." />
        {canSecurity ? (
          <SettingCard href="/platform/settings/security" title="Security" desc="JWT signing keys and security policy." />
        ) : null}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: `settings/billing/page.tsx`** (server, gated `settings.read`)

Static `<Card>`s: Invoice numbering (`INV-YYYY-NNNNNN`), Default plan (sentence + `<Link href="/platform/billing/plans">Manage plans</Link>`), Grace period note. `requirePlatformPermission(user, "settings.read")`. No fetch. `<h1>Billing settings</h1>`.

- [ ] **Step 3: `settings/notifications/page.tsx`** (server, gated `settings.read`)

Single `<Card>`: "Notifications coming soon — email/SMS providers wire up in Phase 3." `<h1>Notification settings</h1>`.

- [ ] **Step 4: `settings/security/page.tsx`** (server, gated `platform.security.jwt_keys.read`)

```tsx
import { Card } from "@sacco/ui";
import type { JwtKeyOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { JwtKeysTable } from "./_components/JwtKeysTable";

export const metadata = { title: "Security settings" };

export default async function SecuritySettingsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.security.jwt_keys.read");

  const { data } = await (
    resources.keys.listJwtKeys() as Promise<{ data?: JwtKeyOut[]; error?: unknown }>
  );

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Security</h1>
      <JwtKeysTable rows={data ?? []} />
      <Card className="p-6 text-[13px] text-[var(--text-secondary)]">
        Signing keys are rotated automatically by a scheduled job. Session TTL and
        password policy are managed via environment configuration.
      </Card>
    </div>
  );
}
```

- [ ] **Step 5: Gate the sidebar Settings link**

In `AppShellSidebar.tsx`, wrap the existing platform `<SidebarItem href="/platform/settings" ... label="Settings" />` in `<PermissionGuard permission="settings.read"> ... </PermissionGuard>` (matching the other platform items).

- [ ] **Step 6: Typecheck + lint; commit.**

Run: `cd admin && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`

```bash
git add "admin/apps/portal/app/platform/(authed)/settings/" admin/apps/portal/src/components/AppShellSidebar.tsx
git commit -m "feat(portal): settings hub + billing/notifications/security pages + sidebar gating

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Verification + PR

- [ ] **Step 1: Per-package gate**

```bash
cd /home/liam/projects/sacco-platform/admin
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/ui test && pnpm --filter @sacco/ui typecheck && pnpm --filter @sacco/ui lint
pnpm --filter @sacco/api-client typecheck
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Record the portal test count (rises by JwtKeysTable cases over SP19's 170).

- [ ] **Step 2: Contract spot-checks**

- [ ] All changes under `admin/` + `docs/` (`git diff --name-only main...HEAD | grep -vE '^(admin/|docs/)'` empty).
- [ ] No backend files touched (`git diff --name-only main...HEAD | grep -E '^(app/|tests/)'` empty).
- [ ] StatusBadge change is additive (union + map + registry row only).

- [ ] **Step 3: Final holistic review** — confirm: hub hides the Security card from non-superusers; security page gated by `platform.security.jwt_keys.read`; keys table is read-only (no actions); billing/notifications are static; sidebar Settings link now gated `settings.read`.

- [ ] **Step 4: Push + PR**

```bash
cd /home/liam/projects/sacco-platform
git push -u origin feat/portal-v1/20-platform-settings
gh pr create --title "feat(portal): platform settings (SP20)" --body "$(cat <<'EOF'
## Summary
- New `/platform/settings` read-only hub completing the 7-nav-group portal inventory: index + Security (real JWT signing-key view from GET /platform/jwt-keys) + Billing (informational + link to Plans) + Notifications (Phase-3 placeholder).
- Pure client; zero backend changes. New `settings.read` (admin) gates the hub/billing/notifications; the existing `platform.security.jwt_keys.read` (superuser) gates Security. Sidebar Settings link now gated.
- Adds a `jwt_key` StatusBadge entity, a `JwtKeyOut` schema, and a `keys` api-client resource.

## Test plan
- `@sacco/schemas` + `@sacco/ui` + `@sacco/portal` test/typecheck/lint green (JwtKeysTable, jwt_key StatusBadge); `@sacco/api-client` typecheck clean.
- All changes under `admin/` (contracts B/N).

> CI note: Lint fails environmentally on this repo (account billing lock); reproduced clean locally. Not a required check.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (author)

- **Spec coverage:** `JwtKeyOut` + `settings.read` → T1; `keys` resource → T2; `jwt_key` StatusBadge → T3; `JwtKeysTable` → T4; 4 pages + sidebar gating → T5; verification/PR → T6. Permission mapping (admin hub / superuser security) enforced in T1 + T5.
- **Type consistency:** `JwtKeyOut` fields (T1) match `JwtKeysTable` (T4) and the security page (T5). `jwt_key` entity (T3) used in T4's status column. `settings.read` (T1) used in T5 pages + sidebar.
- **Verify-at-execution (grep inline):** the exact `resources/index.ts` registration shape; whether `StatusBadge.test.tsx` enumerates entities; `--surface-hover` token (used elsewhere — exists); InvoicesTable slice pattern to mirror for JwtKeysTable.
