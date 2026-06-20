# Tenant Users Management (SP23) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Environment note (2026-06-20):** background subagents can't get Edit approval; run **inline**. Pure client — no backend, no test DB. **Confirm typecheck PASSES before committing** (SP20 lesson: a pre-Read edit can silently fail).

**Goal:** A platform admin manages a tenant's users at `/tenants/[id]/users` — list / create / edit (lock + assign role) / reset password — consuming the existing `tenant_users_admin` backend + api-client.

**Architecture:** Mirrors the SP12 platform-users module (list / new / [userId] / [userId]/edit). Pure client of `resources.tenants.listUsers/getUser/createUser/patchUser/resetUserPassword` + `queryKeys.tenants.users(id)`. Create + reset return a one-time token shown in `<OneTimeModal>`. PATCH is direct (no maker-checker). New `@sacco/schemas` types, a `tenant_user` StatusBadge entity, and two admin permission keys.

**Tech Stack:** Next.js 15 App Router, React 19, TS strict, `@sacco/ui` (DataTable, StatusBadge, FormField, Input, Select, Checkbox, Card, RelativeTime, FormattedDate), `OneTimeModal` (portal), `@sacco/schemas` (Zod + Out type), `@sacco/api-client`, Vitest + Testing Library.

---

## Contract & scope notes (read before starting)

- **Zero new endpoints** (contract B); everything under `admin/` (contract N).
- **api-client (exists):** `resources.tenants.listUsers(id)`, `getUser(id, userId)`, `createUser(id, { email, full_name, is_admin? })`, `patchUser(id, userId, { full_name?, is_active?, is_admin? })`, `resetUserPassword(id, userId)`. All carry the `as never` wart → cast to `{ data?, error? }`.
- **queryKeys (exists):** `queryKeys.tenants.users(id)`.
- **Backend (gates `CurrentAdmin` for all):** `TenantUserOut { id, email, full_name, is_active, is_admin, last_login_at, created_at, updated_at, impersonation_id }`. Create → `{ user, password_reset_token, password_reset_expires_in }` (201). Reset → `{ user_id, password_reset_token, password_reset_expires_in }` (24h). PATCH **direct** (no maker-checker). Shadow users 404 on detail/patch/reset; filtered from the list.
- **`OneTimeModal`** props: `open, onAcknowledge, title, description, payload, payloadLabel?, warningCopy?` (forces acknowledge; no dismiss).
- **Permissions:** add `platform.tenants.users.read → admin` + `platform.tenants.users.write → admin`. UI gating UX-only; API enforces (D).
- **No AuditBar** on the tenant-user detail (tenant-schema record; covered by `/tenants/[id]/audit`). Documented, not a gap.
- **Out of scope:** session panel, shadow users, tenant self-management, e2e + i18n.

## File structure

**`@sacco/schemas`** — create `src/tenant-users.ts`; barrel-export from `index.ts`.
**`@sacco/ui`** — `status-maps.ts` (+ `tenant_user`); `StatusBadge.test.tsx` (+ case).
**`@sacco/portal`**
- `src/auth/permissions.ts` (+ 2 keys).
- `app/platform/(authed)/tenants/[id]/users/page.tsx` + `_components/TenantUsersTable.tsx`.
- `.../users/new/page.tsx` + `_components/CreateTenantUserForm.tsx`.
- `.../users/[userId]/page.tsx` + `_components/ResetPasswordButton.tsx`.
- `.../users/[userId]/edit/page.tsx` + `_components/EditTenantUserForm.tsx`.
- `tenants/[id]/_components/TenantDetail.tsx` + `tenants/[id]/page.tsx` (Users link + `canManageUsers`).
- Tests under `apps/portal/src/__tests__/platform-tenant-users/`.

---

## Task 1: `@sacco/schemas` tenant-user types + `tenant_user` StatusBadge + permissions

**Files:**
- Create: `admin/packages/schemas/src/tenant-users.ts`
- Modify: `admin/packages/schemas/src/index.ts`
- Modify: `admin/packages/ui/src/components/StatusBadge/status-maps.ts`
- Modify: `admin/packages/ui/src/components/StatusBadge/StatusBadge.test.tsx`
- Modify: `admin/apps/portal/src/auth/permissions.ts`
- Test: `admin/packages/schemas/src/__tests__/tenant-users.test.ts`

- [ ] **Step 1: Failing schemas test**

```ts
import { describe, expect, it } from "vitest";
import {
  tenantUserCreateSchema,
  tenantUserPatchSchema,
  tenantUserRoleLabel,
} from "../tenant-users";

describe("tenant-user schemas", () => {
  it("create requires a valid email and non-empty name", () => {
    expect(tenantUserCreateSchema.safeParse({ email: "x", full_name: "A" }).success).toBe(false);
    expect(
      tenantUserCreateSchema.safeParse({ email: "a@b.co", full_name: "Ada", is_admin: true }).success,
    ).toBe(true);
  });
  it("patch accepts a partial body", () => {
    expect(tenantUserPatchSchema.safeParse({ is_active: false }).success).toBe(true);
  });
  it("role label maps is_admin", () => {
    expect(tenantUserRoleLabel(true)).toBe("Admin");
    expect(tenantUserRoleLabel(false)).toBe("Member");
  });
});
```

Run: `cd admin && pnpm --filter @sacco/schemas test -- tenant-users` → FAIL.

- [ ] **Step 2: Create `tenant-users.ts`**

```ts
import { z } from "zod";

// Mirrors app/platform_/tenant_users_admin/schemas.py.
export interface TenantUserOut {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_admin: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
  impersonation_id: string | null;
}

export const tenantUserCreateSchema = z.object({
  email: z.string().trim().toLowerCase().email("Enter a valid email address"),
  full_name: z.string().trim().min(1, "Full name is required").max(200),
  is_admin: z.boolean().default(false),
});
export type TenantUserCreateInput = z.infer<typeof tenantUserCreateSchema>;

export const tenantUserPatchSchema = z.object({
  full_name: z.string().trim().min(1, "Full name is required").max(200).optional(),
  is_active: z.boolean().optional(),
  is_admin: z.boolean().optional(),
});
export type TenantUserPatchInput = z.infer<typeof tenantUserPatchSchema>;

export function tenantUserRoleLabel(isAdmin: boolean): string {
  return isAdmin ? "Admin" : "Member";
}
```

- [ ] **Step 3: Barrel export** — add `export * from "./tenant-users";` to `src/index.ts`.

- [ ] **Step 4: `tenant_user` StatusBadge entity** — in `status-maps.ts`: add `| "tenant_user"` to the `StatusEntity` union; add the map; add the registry row. **Apply all three edits and confirm typecheck before moving on** (the union, the map, and the `ENTITY_MAPS` row must all land — SP20 lesson).

```ts
export const TENANT_USER_STATUS: StatusMap = {
  active: { variant: "success", label: "Active" },
  inactive: { variant: "neutral", label: "Inactive" },
};
```
Registry: `tenant_user: TENANT_USER_STATUS,`. Add a `StatusBadge.test.tsx` case:
```ts
it("maps tenant_user inactive", () => {
  render(<StatusBadge entity="tenant_user" status="inactive" />);
  expect(screen.getByText("Inactive")).toBeInTheDocument();
});
```

- [ ] **Step 5: Permissions** — in `permissions.ts`, after the tenants block (`"platform.tenants.suspend": "admin",`):

```ts
  "platform.tenants.users.read": "admin",
  "platform.tenants.users.write": "admin",
```

- [ ] **Step 6: Run + commit**

Run: `cd admin && pnpm --filter @sacco/schemas test -- tenant-users && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/ui test -- StatusBadge && pnpm --filter @sacco/ui typecheck && pnpm --filter @sacco/portal typecheck`
Expected: all green.

```bash
cd /home/liam/projects/sacco-platform
git add admin/packages/schemas/src/tenant-users.ts admin/packages/schemas/src/index.ts admin/packages/schemas/src/__tests__/tenant-users.test.ts admin/packages/ui/src/components/StatusBadge/ admin/apps/portal/src/auth/permissions.ts
git commit -m "feat(portal): tenant-user schemas + tenant_user StatusBadge + permissions

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `<TenantUsersTable>` + list page

**Files:**
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/users/_components/TenantUsersTable.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/tenants/[id]/users/page.tsx`
- Test: `admin/apps/portal/src/__tests__/platform-tenant-users/TenantUsersTable.test.tsx`

- [ ] **Step 1: Failing test** (mock `useTableUrlState`, per the established DataTable test pattern — copy the full mock from `UsersTable.test.tsx`/`InvoicesTable.test.tsx`)

```tsx
// ...vi.mock("@sacco/ui", ... useTableUrlState ...) as in other DataTable tests...
import { TenantUsersTable } from "../../../app/platform/(authed)/tenants/[id]/users/_components/TenantUsersTable";
import type { TenantUserOut } from "@sacco/schemas";

const rows: TenantUserOut[] = [{
  id: "u1", email: "ada@sacco.test", full_name: "Ada Loan", is_active: true,
  is_admin: true, last_login_at: null, created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z", impersonation_id: null,
}];

describe("TenantUsersTable", () => {
  it("renders email link, role label, and status badge", () => {
    render(<TenantUsersTable rows={rows} tenantId="t1" />);
    expect(screen.getByRole("link", { name: "ada@sacco.test" })).toHaveAttribute(
      "href", "/platform/tenants/t1/users/u1",
    );
    expect(screen.getByText("Admin")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });
  it("shows the empty state", () => {
    render(<TenantUsersTable rows={[]} tenantId="t1" />);
    expect(screen.getByText("No users yet")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement `TenantUsersTable.tsx`** — in-memory DataTable adapter (mirror SP12 `UsersTable`, no filter slot). Props `{ rows: TenantUserOut[]; tenantId: string }`. Columns: Email (`<Link href={/platform/tenants/${tenantId}/users/${row.id}}>`), Name, Role (`tenantUserRoleLabel(is_admin)`), Status (`<StatusBadge entity="tenant_user" status={is_active ? "active" : "inactive"} />`), Last login (`last_login_at ? <RelativeTime> : "Never"`). `id="tenant-users"`, `data={rows}`, `state={{ totalRows: rows.length, isError:false, isPermissionDenied:false }}`, `emptyState={{ title: "No users yet", description: "Add a user to this tenant to get started." }}`. (Slice for pagination like SP12 UsersTable.)

- [ ] **Step 3: Implement `page.tsx`** (server, gated `platform.tenants.users.read`)

```tsx
export default async function TenantUsersPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.users.read");
  const { data } = await (
    resources.tenants.listUsers(id) as Promise<{ data?: TenantUserOut[]; error?: unknown }>
  );
  const canWrite = userHasPermission(user, "platform.tenants.users.write");
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Tenant users</h1>
        {canWrite ? (
          <Button asChild><Link href={`/platform/tenants/${id}/users/new`}>Add user</Link></Button>
        ) : null}
      </div>
      <TenantUsersTable rows={data ?? []} tenantId={id} />
    </div>
  );
}
```

- [ ] **Step 4: Run test + typecheck + lint; commit.**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/[id]/users/page.tsx" "admin/apps/portal/app/platform/(authed)/tenants/[id]/users/_components/TenantUsersTable.tsx" admin/apps/portal/src/__tests__/platform-tenant-users/TenantUsersTable.test.tsx
git commit -m "feat(portal): tenant users list + table

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Create user (`/new`) with one-time token modal

**Files:**
- Create: `.../users/new/page.tsx` + `_components/CreateTenantUserForm.tsx`
- Test: `admin/apps/portal/src/__tests__/platform-tenant-users/CreateTenantUserForm.test.tsx`

- [ ] **Step 1: Failing test** — renders fields; on a mocked successful create the OneTimeModal shows the token.

```tsx
// mock useAuth → resources.tenants.createUser resolving { data: { user, password_reset_token: "TKN-123", password_reset_expires_in: 86400 } }
// mock next/navigation useRouter; render <CreateTenantUserForm tenantId="t1" />
// fill email + name, submit, assert the token "TKN-123" appears (OneTimeModal).
```

Model the mock on SP16/SP12 form tests (mock `@/auth/use-auth`, `useTypedMutation` passthrough or real, `next/navigation`).

- [ ] **Step 2: Implement `CreateTenantUserForm.tsx`** (client) — mirror SP12 `CreateUserForm`: RHF + `zodResolver(tenantUserCreateSchema)`, fields email (`<Input>`), full_name (`<Input>`), is_admin (`<Checkbox>` via FormField). `useTypedMutation` → `resources.tenants.createUser(tenantId, values)` cast `{ data?, error? }`; on success set local state `{ token, ttl }` and open `<OneTimeModal>`; `onAcknowledge` → `router.push(/platform/tenants/${tenantId}/users)` + `toast.success`. On error → `toast.error(apiErrorMessage(...))`.

```tsx
<OneTimeModal
  open={token !== null}
  onAcknowledge={() => { router.push(`/platform/tenants/${tenantId}/users`); }}
  title="User created"
  description="Share this one-time password-reset link with the user out of band. It won't be shown again."
  payload={token ?? ""}
  payloadLabel="Password reset token"
  warningCopy={`Valid for ${Math.round((ttl ?? 0) / 3600)} hours.`}
/>
```

- [ ] **Step 3: Implement `new/page.tsx`** (server, gated write) — `requirePlatformPermission(user, "platform.tenants.users.write")`, `<h1>Add user</h1>`, render `<CreateTenantUserForm tenantId={id} />`.

- [ ] **Step 4: Run + commit.**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/[id]/users/new/" admin/apps/portal/src/__tests__/platform-tenant-users/CreateTenantUserForm.test.tsx
git commit -m "feat(portal): create tenant user + one-time reset-token modal

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Detail (`/[userId]`) + reset-password + edit (`/[userId]/edit`)

**Files:**
- Create: `.../users/[userId]/page.tsx` + `_components/ResetPasswordButton.tsx`
- Create: `.../users/[userId]/edit/page.tsx` + `_components/EditTenantUserForm.tsx`
- Test: `admin/apps/portal/src/__tests__/platform-tenant-users/EditTenantUserForm.test.tsx`

- [ ] **Step 1: Detail `[userId]/page.tsx`** (server, gated read)

`getUser(id, userId)` → `TenantUserOut`; `notFound()` if absent. Read-only `<Card>`: email, name, role label, `<StatusBadge entity="tenant_user">`, last login (`<RelativeTime>`/"Never"), created (`<FormattedDate>`). Header actions when `canWrite`: an **Edit** `<Button asChild><Link .../edit>` + `<ResetPasswordButton tenantId={id} userId={userId} />`. No AuditBar.

- [ ] **Step 2: `ResetPasswordButton.tsx`** (client) — a `<Button>` that calls `resetUserPassword(tenantId, userId)` (cast), and on success opens `<OneTimeModal>` with the returned token + 24h TTL copy. `onAcknowledge` closes it. Error → toast.

- [ ] **Step 3: `EditTenantUserForm.tsx`** (client) — RHF + `zodResolver(tenantUserPatchSchema)`, default values from the passed-in user (`full_name`, `is_active`, `is_admin`). Fields: full_name (`<Input>`), is_active (`<Checkbox>` "Active"), is_admin (`<Checkbox>` "Admin"). `useTypedMutation` → `patchUser(tenantId, userId, values)` (**direct** — no MakerCheckerConfirmDialog) → toast + `router.push` to the detail. The edit page (`[userId]/edit/page.tsx`, server, gated write) fetches the user and renders the form pre-filled.

- [ ] **Step 4: `EditTenantUserForm` test** — pre-fill + a submit calls `patchUser`; assert no maker-checker dialog text appears.

- [ ] **Step 5: Run + commit.**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/[id]/users/[userId]/" admin/apps/portal/src/__tests__/platform-tenant-users/EditTenantUserForm.test.tsx
git commit -m "feat(portal): tenant user detail + reset-password + edit

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: "Users" entry point on TenantDetail

**Files:**
- Modify: `admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx`
- Modify: `admin/apps/portal/app/platform/(authed)/tenants/[id]/page.tsx`
- Modify: `admin/apps/portal/src/__tests__/platform-tenants/TenantDetail.test.tsx`

- [ ] **Step 1: Add `canManageUsers: boolean` prop** to `TenantDetail` and a "Users" link next to the existing "Audit log" link (gated by the prop):

```tsx
{canManageUsers ? (
  <a href={`/platform/tenants/${t.id}/users`} className="text-[13px] text-[var(--text-link)] hover:underline">
    Users
  </a>
) : null}
```

- [ ] **Step 2: Pass it from the page** — `canManageUsers={userHasPermission(user, "platform.tenants.users.read")}`.

- [ ] **Step 3: Update `TenantDetail.test.tsx`** — the `renderDetail` helper must pass `canManageUsers={false}` (TS will flag the missing required prop — the SP19/SP21 pattern).

- [ ] **Step 4: Typecheck + lint + the TenantDetail test; commit.**

```bash
git add "admin/apps/portal/app/platform/(authed)/tenants/[id]/_components/TenantDetail.tsx" "admin/apps/portal/app/platform/(authed)/tenants/[id]/page.tsx" admin/apps/portal/src/__tests__/platform-tenants/TenantDetail.test.tsx
git commit -m "feat(portal): Users link on tenant detail

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Verification + PR

- [ ] **Step 1: Per-package gate**

```bash
cd /home/liam/projects/sacco-platform/admin
pnpm --filter @sacco/schemas test && pnpm --filter @sacco/schemas typecheck && pnpm --filter @sacco/schemas lint
pnpm --filter @sacco/ui test && pnpm --filter @sacco/ui typecheck && pnpm --filter @sacco/ui lint
pnpm --filter @sacco/portal test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Record the portal test count (rises by the TenantUsersTable + CreateTenantUserForm + EditTenantUserForm cases over SP22's 177).

- [ ] **Step 2: Contract spot-checks**

- [ ] All changes under `admin/` + `docs/` (`git diff --name-only main...HEAD | grep -vE '^(admin/|docs/)'` empty).
- [ ] No backend files (`git diff --name-only main...HEAD | grep -E '^(app/|tests/)'` empty).
- [ ] No `MakerCheckerConfirmDialog` in the tenant-users tree (PATCH is direct): `rg "MakerCheckerConfirmDialog" "admin/apps/portal/app/platform/(authed)/tenants/[id]/users"` empty.

- [ ] **Step 3: Final holistic review** — confirm: list links to detail; create + reset show the one-time token in `OneTimeModal` (never in URL/logs — contract F); edit is a direct PATCH (lock = is_active, role = is_admin); "Users" link gated read; no AuditBar on the tenant-user detail.

- [ ] **Step 4: Push + PR**

```bash
cd /home/liam/projects/sacco-platform
git push -u origin feat/portal-v1/23-tenant-users
gh pr create --title "feat(portal): tenant users management (SP23)" --body "$(cat <<'EOF'
## Summary
- New `/platform/tenants/[id]/users` module — list / create / detail / edit (lock + assign role) / reset password — filling the Phase 2 inventory gap. Reached via a "Users" link on the tenant detail page.
- **Pure client; zero backend.** Consumes the existing `tenant_users_admin` backend + `resources.tenants.{listUsers,getUser,createUser,patchUser,resetUserPassword}` + `queryKeys.tenants.users(id)`.
- Create + reset return a one-time password-reset token shown in `<OneTimeModal>` (contract F — never in URL/logs). Edit is a direct PATCH (no maker-checker).

## Notable points
- New `@sacco/schemas` tenant-user types + Zod; a `tenant_user` StatusBadge entity; `platform.tenants.users.read/write` (admin) permissions.
- Shadow/impersonation users are filtered by the backend (404 on detail). No AuditBar on the tenant-user detail (tenant-schema record — covered by `/tenants/[id]/audit`).

## Test plan
- `@sacco/schemas` + `@sacco/ui` + `@sacco/portal` test/typecheck/lint green (schemas, tenant_user badge, TenantUsersTable, Create/Edit forms).
- All changes under `admin/` (contracts B/N).

> CI note: Lint fails environmentally on this repo (account billing lock); reproduced clean locally. Not a required check.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review notes (author)

- **Spec coverage:** schemas + badge + permissions → T1; list → T2; create + token modal → T3; detail + reset + edit → T4; TenantDetail entry point → T5; verify/PR → T6.
- **Type consistency:** `TenantUserOut` (T1) used by TenantUsersTable (T2), forms (T3/T4). `tenantUserCreateSchema`/`tenantUserPatchSchema`/`tenantUserRoleLabel` (T1) consumed in T2/T3/T4. `tenant_user` StatusBadge entity (T1) used in T2/T4. `canManageUsers` prop (T5) matches the page pass-down and the test update.
- **Verify-at-execution (grep inline):** the `useTableUrlState` mock shape (copy from UsersTable.test.tsx); `Checkbox` import + FormField render shape for booleans (check an existing boolean form, e.g. EditUserForm); `OneTimeModal` import path (`@/components/OneTimeModal`); confirm `permissions.ts` tenants block location; the `[id]` vs `[userId]` param names in nested routes (Next requires distinct names — use `[userId]` under `[id]`).
