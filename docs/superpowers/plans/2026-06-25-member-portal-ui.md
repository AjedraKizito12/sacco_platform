# Member Self-Service Portal (UI) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the member-facing self-service portal — members log in and view their own savings, shares, loans, fees, and profile — as a pure client of the Phase 4a `/member/*` API.

**Architecture:** A fourth audience inside the existing `apps/portal` Next.js 15 app, under a real `/member/` path segment with a `(authed)` group, mirroring how `platform/` is organized. Auth plumbing (cookies, server-helpers, route handlers, AuthProvider) clones the operator (`tenant`) variant with a new `member` variant; the shell reuses the operator `AppShell` via a `member` variant. Read types are reused from `@sacco/schemas`.

**Tech Stack:** Next.js 15 App Router, React 19, TypeScript strict, Tailwind v4 + shadcn (forked) via `@sacco/ui`, `@sacco/api-client` (openapi-fetch), `@sacco/schemas` (Zod), TanStack Query/Table, Vitest + RTL, Storybook.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-25-member-portal-ui-design.md`.
- Pure client — **zero backend changes**. All work confined to `admin/` (+ this `docs/` plan). No edits outside `admin/`.
- Contract C: member access token in memory; refresh token in httpOnly Secure SameSite=Strict cookie `sacco_refresh_member`. Never `localStorage`/`sessionStorage`/plain cookies.
- Contract F: set-password/reset tokens come from the URL query only; never logged, never persisted.
- Contract H: money via `<Money>`, dates via the date primitives; never raw `toLocaleString`.
- Contract M: server components fetch via the typed client; client components mutate via TanStack Query.
- Contract T: list screens use the `@sacco/ui` `DataTable`; never hand-roll a `<table>`.
- Read-only v1: no member mutations, no member statement PDF, notification bell stays the empty stub.
- Member JWT audience is `member:<slug>`; member login posts to backend `/member/auth/token` with `X-Tenant-Slug`.
- Tenant slug reuses `resolveTenantSlug` (subdomain prod / `?tenant=` dev / `sacco_tenant_slug` cookie).
- Working dir for all commands: `admin/`. Test: `pnpm --filter @sacco/portal test`, typecheck: `pnpm --filter @sacco/portal typecheck`, lint: `pnpm --filter @sacco/portal lint`. UI package: `pnpm --filter @sacco/ui test`. api-client: `pnpm --filter @sacco/api-client typecheck`.
- Branch: `feat/member-portal/4b` (already created, holds the spec). Commit after every task.

## File-structure map

```
packages/api-client/src/
  resources/memberAuth.ts        (new) login/refresh/logout/me/reset
  resources/member.ts            (new) savings/shares/loans/fees reads
  resources/index.ts             (modify) register memberAuth + member
  query-keys.ts                  (modify) add queryKeys.member.*

apps/portal/src/auth/
  cookies.ts                     (modify) MEMBER_REFRESH_COOKIE + helper unions
  server-helpers.ts              (modify) variant "member"
  server-page-context.ts         (modify) getMemberPageContext()
  AuthProvider.tsx               (modify) initialAuthContext "member"
  (token store)                  (modify) authContext "member" → /api/auth/member-refresh
apps/portal/src/components/
  AppShellSidebar.tsx            (modify) variant "member" + member nav group
  AppShellHeader.tsx             (modify) variant "member"
  forms/LoginForm.tsx            (modify) variant "member"

apps/portal/app/api/auth/
  member-login/route.ts          (new)
  member-refresh/route.ts        (new)
  member-logout/route.ts         (new)
  member-forgot-password/route.ts(new)
  member-reset-password/route.ts (new)

apps/portal/app/member/
  login/page.tsx                 (new)
  set-password/page.tsx          (new)
  forgot-password/page.tsx       (new)
  reset-password/page.tsx        (new)
  (authed)/layout.tsx            (new)
  (authed)/dashboard/page.tsx + _components/  (new)
  (authed)/savings/page.tsx + [id]/page.tsx + _components/  (new)
  (authed)/shares/page.tsx + _components/  (new)
  (authed)/loans/page.tsx + [id]/page.tsx + _components/  (new)
  (authed)/fees/page.tsx + _components/  (new)
  (authed)/profile/page.tsx      (new)

apps/portal/middleware.ts        (modify) /member/* gating
```

---

### Task 1: Member cookies + server-helpers + page context

**Files:**
- Modify: `apps/portal/src/auth/cookies.ts`
- Modify: `apps/portal/src/auth/server-helpers.ts`
- Modify: `apps/portal/src/auth/server-page-context.ts`
- Test: `apps/portal/src/auth/__tests__/member-page-context.test.ts`

**Interfaces:**
- Produces: `MEMBER_REFRESH_COOKIE = "sacco_refresh_member"`, `MEMBER_REFRESH_MAX_AGE = 60*60*8`; `getServerAccessToken("member")`, `getServerCurrentUser("member", token)`; `getMemberPageContext(): Promise<{ member: MemberSelf; slug: string; resources: Resources }>` (redirects `/member/login` when unauthenticated). `MemberSelf` = the `/member/auth/me` shape.

- [ ] **Step 1: Add the member cookie + widen the helper unions**

In `apps/portal/src/auth/cookies.ts`, after `TENANT_REFRESH_COOKIE`:

```ts
export const MEMBER_REFRESH_COOKIE = "sacco_refresh_member";
```

and after `TENANT_REFRESH_MAX_AGE`:

```ts
export const MEMBER_REFRESH_MAX_AGE = 60 * 60 * 8; // 8 hours
```

Widen the cookie-name unions in `SetRefreshArgs.name`, `clearRefreshCookie`, and `readRefreshCookie` from
`typeof PLATFORM_REFRESH_COOKIE | typeof TENANT_REFRESH_COOKIE` to also include
`| typeof MEMBER_REFRESH_COOKIE`.

- [ ] **Step 2: Write the failing page-context test**

```ts
// apps/portal/src/auth/__tests__/member-page-context.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";

const redirectMock = vi.fn((url: string) => {
  throw new Error(`REDIRECT:${url}`);
});
vi.mock("next/navigation", () => ({ redirect: redirectMock }));

const getServerAccessToken = vi.fn();
const getServerCurrentUser = vi.fn();
const getServerTenantSlug = vi.fn();
vi.mock("../server-helpers", () => ({
  getServerAccessToken: (...a: unknown[]) => getServerAccessToken(...a),
  getServerCurrentUser: (...a: unknown[]) => getServerCurrentUser(...a),
  getServerTenantSlug: (...a: unknown[]) => getServerTenantSlug(...a),
}));

import { getMemberPageContext } from "../server-page-context";

beforeEach(() => {
  redirectMock.mockClear();
  getServerAccessToken.mockReset();
  getServerCurrentUser.mockReset();
  getServerTenantSlug.mockReset();
});

it("redirects to /member/login when no access token", async () => {
  getServerTenantSlug.mockResolvedValue("acme");
  getServerAccessToken.mockResolvedValue({ accessToken: null });
  await expect(getMemberPageContext()).rejects.toThrow("REDIRECT:/member/login");
});

it("returns member + slug + resources when authenticated", async () => {
  getServerTenantSlug.mockResolvedValue("acme");
  getServerAccessToken.mockResolvedValue({ accessToken: "tok" });
  getServerCurrentUser.mockResolvedValue({ id: "m1", full_name: "Jane" });
  const ctx = await getMemberPageContext();
  expect(ctx.slug).toBe("acme");
  expect(ctx.member).toMatchObject({ id: "m1" });
  expect(ctx.resources).toBeTruthy();
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- member-page-context`
Expected: FAIL — `getMemberPageContext` not exported.

- [ ] **Step 4: Extend server-helpers for the member variant**

In `apps/portal/src/auth/server-helpers.ts`:

1. Import `MEMBER_REFRESH_COOKIE` alongside the others.
2. Widen both `cache(async (variant: "platform" | "tenant") ...)` signatures (in `getServerAccessToken` and `getServerCurrentUser`) to `"platform" | "tenant" | "member"`.
3. In `getServerAccessToken`: choose the cookie + endpoint for member:
```ts
   const refreshCookieName =
     variant === "platform"
       ? PLATFORM_REFRESH_COOKIE
       : variant === "tenant"
         ? TENANT_REFRESH_COOKIE
         : MEMBER_REFRESH_COOKIE;
   // ...
   const endpoint =
     variant === "platform"
       ? "/platform/auth/refresh"
       : variant === "tenant"
         ? "/auth/refresh"
         : "/member/auth/refresh";
```
   And the `X-Tenant-Slug` header must be sent for `tenant` **and** `member`:
```ts
   if (variant === "tenant" || variant === "member") {
     const slug = await getServerTenantSlug();
     if (!slug) return { accessToken: null, expiresIn: null };
     headersInit["X-Tenant-Slug"] = slug;
   }
```
4. In `getServerCurrentUser`: endpoint for member is `/member/auth/me`, and send `X-Tenant-Slug` for member too:
```ts
   const endpoint =
     variant === "platform"
       ? "/platform/auth/me"
       : variant === "tenant"
         ? "/auth/me"
         : "/member/auth/me";
   // ...
   if (variant === "tenant" || variant === "member") {
     const slug = await getServerTenantSlug();
     if (slug) headersInit["X-Tenant-Slug"] = slug;
   }
```

- [ ] **Step 5: Add getMemberPageContext**

In `apps/portal/src/auth/server-page-context.ts`, add after `getTenantPageContext`:

```ts
export interface MemberSelf {
  id: string;
  member_number: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  status: string;
  date_of_birth: string;
  gender: string;
  joined_at: string | null;
  last_login_at: string | null;
}

export interface MemberPageContext {
  member: MemberSelf;
  slug: string;
  resources: Resources;
}

export async function getMemberPageContext(): Promise<MemberPageContext> {
  const slug = await getServerTenantSlug();
  const { accessToken } = await getServerAccessToken("member");
  if (!slug || !accessToken) redirect("/member/login");
  const member = (await getServerCurrentUser(
    "member",
    accessToken,
  )) as unknown as MemberSelf | null;
  if (!member) redirect("/member/login");

  const store = new InMemoryTokenStore("/member/auth/refresh");
  store.setAccessToken(accessToken);
  const client = createApiClient({
    baseUrl: API_BASE,
    tokenStore: store,
    tenantContext: new FixedTenantContext(slug),
  });
  return { member, slug, resources: buildResources(client) };
}
```

(`getServerCurrentUser` returns `CurrentUserShape`; the member `/me` shape differs, so cast through `unknown` to `MemberSelf` — the runtime payload is the 4a `MemberOut`.)

- [ ] **Step 6: Run test + typecheck + lint**

Run: `cd admin && pnpm --filter @sacco/portal test -- member-page-context && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: PASS + clean.

- [ ] **Step 7: Commit**

```bash
git add apps/portal/src/auth/cookies.ts apps/portal/src/auth/server-helpers.ts apps/portal/src/auth/server-page-context.ts apps/portal/src/auth/__tests__/member-page-context.test.ts
git commit -m "feat(portal): member auth server helpers + getMemberPageContext"
```

---

### Task 2: Member auth route handlers

**Files:**
- Create: `apps/portal/app/api/auth/member-login/route.ts`
- Create: `apps/portal/app/api/auth/member-refresh/route.ts`
- Create: `apps/portal/app/api/auth/member-logout/route.ts`
- Create: `apps/portal/app/api/auth/member-forgot-password/route.ts`
- Create: `apps/portal/app/api/auth/member-reset-password/route.ts`
- Test: `apps/portal/src/__tests__/member-login-route.test.ts`

**Interfaces:**
- Consumes: `MEMBER_REFRESH_COOKIE`, `MEMBER_REFRESH_MAX_AGE` (Task 1), cookie helpers, `loginSchema` from `@sacco/schemas`.
- Produces: `POST /api/auth/member-login|member-refresh|member-logout|member-forgot-password|member-reset-password`.

- [ ] **Step 1: Write the failing route test (clone the operator one)**

Read `apps/portal/src/__tests__/tenant-login-route.test.ts` and clone it to
`member-login-route.test.ts`, changing the import to `app/api/auth/member-login/route`,
the upstream URL assertion to `/member/auth/token`, and the cookie assertion to
`sacco_refresh_member`. Keep the same cases: 400 on invalid body, 400 on missing
slug, sets refresh cookie + returns access token on success, passes through
upstream error status.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- member-login-route`
Expected: FAIL — route module does not exist.

- [ ] **Step 3: Write member-login (clone tenant-login)**

Clone `apps/portal/app/api/auth/tenant-login/route.ts` to
`apps/portal/app/api/auth/member-login/route.ts` with these exact substitutions:
- import `MEMBER_REFRESH_COOKIE`, `MEMBER_REFRESH_MAX_AGE` instead of the tenant ones;
- upstream `fetch(`${API_BASE}/member/auth/token`, ...)` (was `/auth/token`);
- `setRefreshCookie({ name: MEMBER_REFRESH_COOKIE, value: data.refresh_token, maxAgeSeconds: MEMBER_REFRESH_MAX_AGE })`.
Keep slug resolution (`x-sacco-tenant-slug` header → `getTenantSlugCookie()`), `loginSchema` validation, `setTenantSlugCookie(tenantSlug)`, and the response shape unchanged.

- [ ] **Step 4: Write the other four handlers (clone tenant-*)**

- `member-refresh/route.ts` ← clone `tenant-refresh/route.ts`: upstream `/member/auth/refresh`, read `MEMBER_REFRESH_COOKIE`, send `X-Tenant-Slug`.
- `member-logout/route.ts` ← clone `tenant-logout/route.ts`: upstream `/member/auth/logout`, clear `MEMBER_REFRESH_COOKIE`.
- `member-forgot-password/route.ts` ← clone `tenant-forgot-password/route.ts`: upstream `/member/auth/password-reset/request` (always returns 204; do not leak existence).
- `member-reset-password/route.ts` ← clone `tenant-reset-password/route.ts`: upstream `/member/auth/password-reset/confirm`, body `{ token, new_password }`.

For each, verify the operator analog's exact request/response shaping and reuse it; only the cookie name, upstream path, and slug handling change.

- [ ] **Step 5: Run test + typecheck + lint**

Run: `cd admin && pnpm --filter @sacco/portal test -- member-login-route && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: PASS + clean.

- [ ] **Step 6: Commit**

```bash
git add apps/portal/app/api/auth/member-login apps/portal/app/api/auth/member-refresh apps/portal/app/api/auth/member-logout apps/portal/app/api/auth/member-forgot-password apps/portal/app/api/auth/member-reset-password apps/portal/src/__tests__/member-login-route.test.ts
git commit -m "feat(portal): member auth route handlers"
```

---

### Task 3: AuthProvider + token store + LoginForm member context

**Files:**
- Modify: `apps/portal/src/auth/AuthProvider.tsx`
- Modify: the api-client token store (find with `grep -rl "setAuthContext" packages/api-client/src`)
- Modify: `apps/portal/src/components/forms/LoginForm.tsx`
- Test: `apps/portal/src/components/forms/__tests__/LoginForm.member.test.tsx`

**Interfaces:**
- Consumes: route handlers (Task 2).
- Produces: `AuthProvider` accepts `initialAuthContext="member"`; the token store maps `authContext="member"` → client refresh path `/api/auth/member-refresh`; `<LoginForm variant="member" />` posts to `/api/auth/member-login`.

- [ ] **Step 1: Write the failing LoginForm test**

```tsx
// apps/portal/src/components/forms/__tests__/LoginForm.member.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

import { LoginForm } from "../LoginForm";

beforeEach(() => {
  push.mockClear();
  fetchMock.mockReset();
});

it("member variant posts to /api/auth/member-login and redirects to dashboard", async () => {
  fetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({ access_token: "a", expires_in: 900 }),
  });
  render(<LoginForm variant="member" />);
  fireEvent.change(screen.getByLabelText(/email/i), {
    target: { value: "jane@example.com" },
  });
  fireEvent.change(screen.getByLabelText(/password/i), {
    target: { value: "S3cret-pass!ok" },
  });
  fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/member-login",
      expect.objectContaining({ method: "POST" }),
    ),
  );
});
```

(Verify the operator `LoginForm` test for the exact success-path redirect target and adjust the post-login assertion: member should land on `/member/dashboard`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- LoginForm.member`
Expected: FAIL — `variant="member"` not handled.

- [ ] **Step 3: Extend LoginForm**

Read `apps/portal/src/components/forms/LoginForm.tsx`. It maps `variant` → login endpoint + post-login redirect. Add the `member` case:
- endpoint `/api/auth/member-login`;
- on success redirect to `/member/dashboard`;
- forgot-password link → `/member/forgot-password`.
Widen the `variant` prop type to include `"member"`.

- [ ] **Step 4: Extend AuthProvider + token store**

In `apps/portal/src/auth/AuthProvider.tsx`: widen `initialAuthContext?: "platform" | "tenant" | "member"`.
In the api-client token store (the file with `setAuthContext`): widen the auth-context union to include `"member"` and map it to the client refresh path `/api/auth/member-refresh` (mirror the existing `tenant` → `/api/auth/tenant-refresh` entry — confirm the exact tenant mapping and replicate it for member).

- [ ] **Step 5: Run test + typecheck + lint (portal + api-client)**

Run: `cd admin && pnpm --filter @sacco/portal test -- LoginForm.member && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/api-client typecheck && pnpm --filter @sacco/portal lint`
Expected: PASS + clean.

- [ ] **Step 6: Commit**

```bash
git add apps/portal/src/auth/AuthProvider.tsx apps/portal/src/components/forms/LoginForm.tsx apps/portal/src/components/forms/__tests__/LoginForm.member.test.tsx packages/api-client/src
git commit -m "feat(portal): member auth context in AuthProvider/token-store/LoginForm"
```

---

### Task 4: api-client member resources + query keys

**Files:**
- Create: `packages/api-client/src/resources/memberAuth.ts`
- Create: `packages/api-client/src/resources/member.ts`
- Modify: `packages/api-client/src/resources/index.ts`
- Modify: `packages/api-client/src/query-keys.ts`
- Test: `packages/api-client/src/__tests__/member-resources.test.ts`

**Interfaces:**
- Produces: `resources.memberAuth.{login,refresh,logout,me,resetRequest,resetConfirm}`; `resources.member.{listSavings,getSavingsTransactions,listShares,listLoans,getLoan,getLoanSchedule,getLoanStatement,listFees}`; `queryKeys.member.{savings,savingsTransactions,shares,loans,loan,loanSchedule,loanStatement,fees}`.

- [ ] **Step 1: Write the failing resource test**

```ts
// packages/api-client/src/__tests__/member-resources.test.ts
import { describe, it, expect, vi } from "vitest";
import { member } from "../resources/member";

it("listSavings hits /member/savings", () => {
  const api = { GET: vi.fn(), POST: vi.fn() } as never;
  member(api as never).listSavings();
  expect((api as { GET: ReturnType<typeof vi.fn> }).GET).toHaveBeenCalledWith(
    "/member/savings",
    expect.anything(),
  );
});

it("getLoanStatement hits the statement path", () => {
  const api = { GET: vi.fn(), POST: vi.fn() } as never;
  member(api as never).getLoanStatement("loan-1");
  expect((api as { GET: ReturnType<typeof vi.fn> }).GET).toHaveBeenCalledWith(
    "/member/loans/{loan_id}/statement",
    expect.anything(),
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/api-client test -- member-resources`
Expected: FAIL — `../resources/member` missing.

- [ ] **Step 3: Write the member read resource**

```ts
// packages/api-client/src/resources/member.ts
import type { FetchClient } from "../client";

export function member(api: FetchClient) {
  return {
    listSavings: (query?: Record<string, unknown>) =>
      api.GET("/member/savings" as never, { params: { query } } as never),
    getSavingsTransactions: (accountId: string) =>
      api.GET("/member/savings/{account_id}/transactions" as never, {
        params: { path: { account_id: accountId } },
      } as never),
    listShares: (query?: Record<string, unknown>) =>
      api.GET("/member/shares" as never, { params: { query } } as never),
    listLoans: (query?: Record<string, unknown>) =>
      api.GET("/member/loans" as never, { params: { query } } as never),
    getLoan: (loanId: string) =>
      api.GET("/member/loans/{loan_id}" as never, {
        params: { path: { loan_id: loanId } },
      } as never),
    getLoanSchedule: (loanId: string) =>
      api.GET("/member/loans/{loan_id}/schedule" as never, {
        params: { path: { loan_id: loanId } },
      } as never),
    getLoanStatement: (loanId: string) =>
      api.GET("/member/loans/{loan_id}/statement" as never, {
        params: { path: { loan_id: loanId } },
      } as never),
    listFees: (query?: Record<string, unknown>) =>
      api.GET("/member/fees" as never, { params: { query } } as never),
  } as const;
}
```

- [ ] **Step 4: Write the member auth resource**

```ts
// packages/api-client/src/resources/memberAuth.ts
import type { FetchClient } from "../client";

export function memberAuth(api: FetchClient) {
  return {
    login: (body: Record<string, unknown>) =>
      api.POST("/member/auth/token" as never, { body } as never),
    refresh: (body: Record<string, unknown>) =>
      api.POST("/member/auth/refresh" as never, { body } as never),
    logout: () => api.POST("/member/auth/logout" as never, {} as never),
    me: () => api.GET("/member/auth/me" as never, {} as never),
    resetRequest: (body: Record<string, unknown>) =>
      api.POST("/member/auth/password-reset/request" as never, { body } as never),
    resetConfirm: (body: Record<string, unknown>) =>
      api.POST("/member/auth/password-reset/confirm" as never, { body } as never),
  } as const;
}
```

- [ ] **Step 5: Register in buildResources + add query keys**

In `packages/api-client/src/resources/index.ts`: import `member` and `memberAuth`, add `member: member(api),` and `memberAuth: memberAuth(api),` to the returned object.

In `packages/api-client/src/query-keys.ts`, add to the `queryKeys` object:

```ts
  member: {
    root: () => ["member"] as const,
    savings: () => ["member", "savings"] as const,
    savingsTransactions: (id: string) =>
      ["member", "savings", id, "transactions"] as const,
    shares: () => ["member", "shares"] as const,
    loans: () => ["member", "loans"] as const,
    loan: (id: string) => ["member", "loan", id] as const,
    loanSchedule: (id: string) => ["member", "loan", id, "schedule"] as const,
    loanStatement: (id: string) => ["member", "loan", id, "statement"] as const,
    fees: () => ["member", "fees"] as const,
  },
```

- [ ] **Step 6: Run test + typecheck**

Run: `cd admin && pnpm --filter @sacco/api-client test -- member-resources && pnpm --filter @sacco/api-client typecheck`
Expected: PASS + clean.

- [ ] **Step 7: Commit**

```bash
git add packages/api-client/src/resources/member.ts packages/api-client/src/resources/memberAuth.ts packages/api-client/src/resources/index.ts packages/api-client/src/query-keys.ts packages/api-client/src/__tests__/member-resources.test.ts
git commit -m "feat(api-client): member self-service + member-auth resources"
```

---

### Task 5: AppShell member variant

**Files:**
- Modify: `apps/portal/src/components/AppShellSidebar.tsx`
- Modify: `apps/portal/src/components/AppShellHeader.tsx`
- Test: `apps/portal/src/components/__tests__/AppShellSidebar.member.test.tsx`
- Story: `packages/ui/src/components/Shell/Sidebar.stories.tsx` (add a member-nav story) — only if the sidebar nav config lives in `@sacco/ui`; if it lives in the app component, add an app-level story or skip per existing convention.

**Interfaces:**
- Consumes: nothing new.
- Produces: `<AppShellSidebar variant="member" />` renders the member nav (Dashboard, Savings, Shares, Loans, Fees, Profile linking `/member/*`); `<AppShellHeader variant="member" tenantName={slug} />` renders member chrome (no command palette; bell stays the stub).

- [ ] **Step 1: Write the failing sidebar test**

```tsx
// apps/portal/src/components/__tests__/AppShellSidebar.member.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
vi.mock("next/navigation", () => ({ usePathname: () => "/member/dashboard" }));

import { AppShellSidebar } from "../AppShellSidebar";

it("renders member nav links", () => {
  render(<AppShellSidebar variant="member" />);
  for (const label of ["Dashboard", "Savings", "Shares", "Loans", "Fees", "Profile"]) {
    expect(screen.getByText(label)).toBeInTheDocument();
  }
  // member nav never exposes operator destinations
  expect(screen.queryByText("Approvals")).not.toBeInTheDocument();
  expect(screen.queryByText("Audit")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- AppShellSidebar.member`
Expected: FAIL — `variant="member"` unhandled.

- [ ] **Step 3: Add the member variant**

Read `apps/portal/src/components/AppShellSidebar.tsx`. It branches on `variant` (`"platform" | "tenant"`) to choose nav groups. Add `"member"` to the variant union and a member nav group:

```tsx
const MEMBER_NAV = [
  { label: "Dashboard", href: "/member/dashboard", icon: LayoutDashboard },
  { label: "Savings", href: "/member/savings", icon: PiggyBank },
  { label: "Shares", href: "/member/shares", icon: TrendingUp },
  { label: "Loans", href: "/member/loans", icon: Banknote },
  { label: "Fees", href: "/member/fees", icon: Receipt },
  { label: "Profile", href: "/member/profile", icon: User },
];
```

(Use the lucide icons already imported in the file; import any missing ones following the existing import style. Match the file's existing nav-group data shape exactly — if it uses JSX `<>...</>` groups rather than arrays, follow that form.)

In `apps/portal/src/components/AppShellHeader.tsx`: add `"member"` to the variant union; for member, render the same header as tenant but omit the command-palette trigger (the bell stub already renders for all variants). Keep `tenantName` display.

- [ ] **Step 4: Run test + typecheck + lint**

Run: `cd admin && pnpm --filter @sacco/portal test -- AppShellSidebar.member && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: PASS + clean.

- [ ] **Step 5: Commit**

```bash
git add apps/portal/src/components/AppShellSidebar.tsx apps/portal/src/components/AppShellHeader.tsx apps/portal/src/components/__tests__/AppShellSidebar.member.test.tsx
git commit -m "feat(portal): AppShell member variant + member nav"
```

---

### Task 6: Member auth pages (login / set-password / forgot / reset)

**Files:**
- Create: `apps/portal/app/member/login/page.tsx`
- Create: `apps/portal/app/member/set-password/page.tsx`
- Create: `apps/portal/app/member/forgot-password/page.tsx`
- Create: `apps/portal/app/member/reset-password/page.tsx`
- Test: `apps/portal/app/member/__tests__/auth-pages.test.tsx`

**Interfaces:**
- Consumes: `<LoginForm variant="member" />` (Task 3), the existing reset/forgot forms.
- Produces: public member auth routes.

- [ ] **Step 1: Write the failing page test**

```tsx
// apps/portal/app/member/__tests__/auth-pages.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

import MemberLogin from "../login/page";

it("member login renders the sign-in form", () => {
  render(<MemberLogin />);
  expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- auth-pages`
Expected: FAIL — `../login/page` missing.

- [ ] **Step 3: Write login page (clone operator login)**

```tsx
// apps/portal/app/member/login/page.tsx
import { LoginForm } from "@/components/forms/LoginForm";

export default function MemberLogin() {
  return (
    <main className="mx-auto grid min-h-screen max-w-3xl place-items-center p-8">
      <LoginForm variant="member" />
    </main>
  );
}
```

- [ ] **Step 4: Write set-password / forgot / reset pages**

Read the operator analogs `apps/portal/app/(tenant)/reset-password/page.tsx` and
`apps/portal/app/(tenant)/forgot-password/page.tsx` and the forms they use
(`ResetPasswordForm`, `ForgotPasswordForm`). Create:

- `member/forgot-password/page.tsx`: renders `<ForgotPasswordForm variant="member" />` (extend the form's variant union to post to `/api/auth/member-forgot-password`, mirroring the tenant case — apply the same one-line variant addition the operator form uses).
- `member/reset-password/page.tsx`: renders `<ResetPasswordForm variant="member" />` (posts to `/api/auth/member-reset-password`; reads `?token=` from `useSearchParams`).
- `member/set-password/page.tsx`: same `<ResetPasswordForm variant="member" />` but with set-password copy ("Set your password") — reuse the reset form (the backend confirm endpoint is identical); the page passes a `mode="set"` or a `title` prop if the form supports it, otherwise render the form with a heading above it. Read the token from `?token=` only (contract F).

For each form variant addition, make the same minimal change the operator path uses (endpoint switch on `variant`), widening the variant prop to include `"member"`.

- [ ] **Step 5: Run test + typecheck + lint**

Run: `cd admin && pnpm --filter @sacco/portal test -- auth-pages && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: PASS + clean.

- [ ] **Step 6: Commit**

```bash
git add apps/portal/app/member/login apps/portal/app/member/set-password apps/portal/app/member/forgot-password apps/portal/app/member/reset-password apps/portal/app/member/__tests__ apps/portal/src/components/forms
git commit -m "feat(portal): member auth pages (login/set-password/forgot/reset)"
```

---

### Task 7: (authed) layout + middleware gating

**Files:**
- Create: `apps/portal/app/member/(authed)/layout.tsx`
- Modify: `apps/portal/middleware.ts`
- Test: `apps/portal/app/member/(authed)/__tests__/layout.test.tsx`

**Interfaces:**
- Consumes: `getServerAccessToken("member")`, `getServerCurrentUser("member")`, `getServerTenantSlug`, `AuthProvider`, `AppShellHeader/Sidebar` member variant.
- Produces: the authed member layout (redirects `/member/login` when unauthenticated) + middleware that routes unauthenticated `/member/*` page requests to `/member/login`.

- [ ] **Step 1: Write the failing layout test**

```tsx
// apps/portal/app/member/(authed)/__tests__/layout.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";

const redirect = vi.fn((u: string) => { throw new Error(`REDIRECT:${u}`); });
vi.mock("next/navigation", () => ({ redirect }));
const getServerAccessToken = vi.fn();
const getServerCurrentUser = vi.fn();
const getServerTenantSlug = vi.fn();
vi.mock("@/auth/server-helpers", () => ({
  getServerAccessToken: (...a: unknown[]) => getServerAccessToken(...a),
  getServerCurrentUser: (...a: unknown[]) => getServerCurrentUser(...a),
  getServerTenantSlug: (...a: unknown[]) => getServerTenantSlug(...a),
}));

import MemberAuthedLayout from "../layout";

beforeEach(() => {
  redirect.mockClear();
  getServerTenantSlug.mockResolvedValue("acme");
});

it("redirects to /member/login with no token", async () => {
  getServerAccessToken.mockResolvedValue({ accessToken: null });
  await expect(
    MemberAuthedLayout({ children: null }),
  ).rejects.toThrow("REDIRECT:/member/login");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- "member/(authed)"`
Expected: FAIL — layout missing.

- [ ] **Step 3: Write the authed layout (clone the tenant-authed layout)**

Clone `apps/portal/app/(tenant-authed)/layout.tsx` to
`apps/portal/app/member/(authed)/layout.tsx` with these changes:
- redirect target `/member/login`;
- `getServerAccessToken("member")` / `getServerCurrentUser("member", accessToken)`;
- `AuthProvider initialAuthContext="member"`;
- `AppShellHeader variant="member"` / `AppShellSidebar variant="member"`;
- drop the impersonation cookie/banner block entirely (operator-only);
- keep `TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala"` and `PortalUserProvider user={member}` (cast member to the provider's expected user shape, or pass the minimal `{ id, full_name }` the provider needs — confirm `PortalUserProvider` prop type and adapt).

- [ ] **Step 4: Extend middleware for /member gating**

Read `apps/portal/middleware.ts`. It already resolves the slug and persists the
cookie. Add a guard: for a request whose `pathname` starts with `/member/` and is
not a public member auth page (`/member/login`, `/member/set-password`,
`/member/forgot-password`, `/member/reset-password`), if there is no
`sacco_refresh_member` cookie, redirect to `/member/login`. Mirror the existing
operator/platform redirect logic in the same file (find the block that redirects
unauthenticated tenant/platform page requests and add the member branch with the
same shape). Do not gate `/api/*` (the matcher already excludes it).

- [ ] **Step 5: Run test + typecheck + lint**

Run: `cd admin && pnpm --filter @sacco/portal test -- "member/(authed)" && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: PASS + clean.

- [ ] **Step 6: Commit**

```bash
git add "apps/portal/app/member/(authed)/layout.tsx" "apps/portal/app/member/(authed)/__tests__" apps/portal/middleware.ts
git commit -m "feat(portal): member authed layout + middleware gating"
```

---

### Task 8: Dashboard

**Files:**
- Create: `apps/portal/app/member/(authed)/dashboard/page.tsx`
- Create: `apps/portal/app/member/(authed)/dashboard/_components/SummaryTiles.tsx`
- Test: `apps/portal/app/member/(authed)/dashboard/__tests__/SummaryTiles.test.tsx`

**Interfaces:**
- Consumes: `getMemberPageContext()` (Task 1), `resources.member.*` (Task 4).
- Produces: `/member/dashboard` summary home.

- [ ] **Step 1: Write the failing tiles test**

```tsx
// .../dashboard/__tests__/SummaryTiles.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TenantCurrencyProvider } from "@sacco/ui";
import { SummaryTiles } from "../_components/SummaryTiles";

function wrap(ui: React.ReactNode) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      {ui}
    </TenantCurrencyProvider>,
  );
}

it("renders the four headline tiles with computed values", () => {
  wrap(
    <SummaryTiles
      savingsTotal="1240000.00"
      sharesHeld={120}
      sharesValue="1200000.00"
      activeLoans={1}
      feesOutstanding="20000.00"
    />,
  );
  expect(screen.getByText(/Savings/i)).toBeInTheDocument();
  expect(screen.getByText(/Shares/i)).toBeInTheDocument();
  expect(screen.getByText(/Loans/i)).toBeInTheDocument();
  expect(screen.getByText(/Fees/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- SummaryTiles`
Expected: FAIL — component missing.

- [ ] **Step 3: Write SummaryTiles (presentational)**

```tsx
// .../dashboard/_components/SummaryTiles.tsx
import Link from "next/link";
import { Money, Count } from "@sacco/ui";

interface Props {
  savingsTotal: string;
  sharesHeld: number;
  sharesValue: string;
  activeLoans: number;
  feesOutstanding: string;
}

export function SummaryTiles(props: Props) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <Link href="/member/savings" className="rounded-lg border p-4">
        <div className="text-sm text-[var(--text-muted)]">Savings</div>
        <Money amount={props.savingsTotal} />
      </Link>
      <Link href="/member/shares" className="rounded-lg border p-4">
        <div className="text-sm text-[var(--text-muted)]">Shares</div>
        <div><Count value={props.sharesHeld} /> · <Money amount={props.sharesValue} /></div>
      </Link>
      <Link href="/member/loans" className="rounded-lg border p-4">
        <div className="text-sm text-[var(--text-muted)]">Active loans</div>
        <Count value={props.activeLoans} />
      </Link>
      <Link href="/member/fees" className="rounded-lg border p-4">
        <div className="text-sm text-[var(--text-muted)]">Fees outstanding</div>
        <Money amount={props.feesOutstanding} />
      </Link>
    </div>
  );
}
```

(Confirm `<Money>` takes `amount` and `<Count>` takes `value` — verified in Phase 3. Confirm the `--text-muted` token exists; if not, use `--text-secondary` per the token file.)

- [ ] **Step 4: Write the dashboard page (server component)**

```tsx
// .../dashboard/page.tsx
import { getMemberPageContext } from "@/auth/server-page-context";
import { SummaryTiles } from "./_components/SummaryTiles";

export default async function MemberDashboard() {
  const { member, resources } = await getMemberPageContext();
  const [savings, shares, loans, fees] = await Promise.all([
    resources.member.listSavings(),
    resources.member.listShares(),
    resources.member.listLoans(),
    resources.member.listFees(),
  ]);

  const savingsRows = (savings.data ?? []) as Array<{ available_balance?: string; balance?: string }>;
  const shareRows = (shares.data ?? []) as Array<{ shares_held: number; total_value: string }>;
  const loanRows = (loans.data ?? []) as Array<{ status: string }>;
  const feeRows = (fees.data ?? []) as Array<{ status: string; amount: string }>;

  const sum = (xs: string[]) =>
    xs.reduce((acc, v) => acc + Number(v || "0"), 0).toFixed(2);

  const savingsTotal = sum(savingsRows.map((a) => a.available_balance ?? a.balance ?? "0"));
  const sharesHeld = shareRows.reduce((acc, s) => acc + (s.shares_held ?? 0), 0);
  const sharesValue = sum(shareRows.map((s) => s.total_value ?? "0"));
  const activeLoans = loanRows.filter((l) =>
    ["disbursed", "in_arrears"].includes(l.status),
  ).length;
  const feesOutstanding = sum(
    feeRows.filter((f) => f.status !== "paid" && f.status !== "waived").map((f) => f.amount),
  );

  return (
    <div className="space-y-6">
      <h1 className="text-[length:var(--text-h4)] font-semibold">Welcome, {member.full_name}</h1>
      <SummaryTiles
        savingsTotal={savingsTotal}
        sharesHeld={sharesHeld}
        sharesValue={sharesValue}
        activeLoans={activeLoans}
        feesOutstanding={feesOutstanding}
      />
    </div>
  );
}
```

(At build time, confirm the exact field names on the member savings list response — the operator `SavingsAccountOut` is the same shape; adjust `available_balance`/`balance` to whichever the schema exposes. Confirm the `--text-h4` token name against `packages/ui/src/tokens.css`.)

- [ ] **Step 5: Run test + typecheck + lint**

Run: `cd admin && pnpm --filter @sacco/portal test -- SummaryTiles && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: PASS + clean.

- [ ] **Step 6: Commit**

```bash
git add "apps/portal/app/member/(authed)/dashboard"
git commit -m "feat(portal): member dashboard summary home"
```

---

### Task 9: Savings (list + detail)

**Files:**
- Create: `apps/portal/app/member/(authed)/savings/page.tsx`
- Create: `apps/portal/app/member/(authed)/savings/[id]/page.tsx`
- Create: `apps/portal/app/member/(authed)/savings/_components/MemberSavingsTable.tsx`
- Create: `apps/portal/app/member/(authed)/savings/[id]/_components/MemberTransactionsTable.tsx`
- Test: `apps/portal/app/member/(authed)/savings/__tests__/MemberSavingsTable.test.tsx`

**Interfaces:**
- Consumes: `getMemberPageContext`, `resources.member.{listSavings,getSavingsTransactions}`, `@sacco/ui` `DataTable`.
- Produces: `/member/savings` + `/member/savings/[id]`.

- [ ] **Step 1: Write the failing table test**

Clone the operator savings table test pattern. Read
`apps/portal/app/(tenant-authed)/savings/_components/` for the operator
`SavingsAccountsTable` and its test (the `vi.mock("@sacco/ui", ... useTableUrlState)` block is required — every DataTable test uses it). Write:

```tsx
// .../savings/__tests__/MemberSavingsTable.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { TenantCurrencyProvider } from "@sacco/ui";

// Mirror the operator DataTable test mock for useTableUrlState (copy from the
// operator SavingsAccountsTable.test.tsx in (tenant-authed)/savings/_components).

import { MemberSavingsTable } from "../_components/MemberSavingsTable";

it("renders a row per account", () => {
  render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <MemberSavingsTable
        rows={[{ id: "a1", product_name: "Regular", available_balance: "1000.00" } as never]}
      />
    </TenantCurrencyProvider>,
  );
  expect(screen.getByText("Regular")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- MemberSavingsTable`
Expected: FAIL — component missing.

- [ ] **Step 3: Write MemberSavingsTable**

Clone the operator `SavingsAccountsTable` (in `(tenant-authed)/savings/_components/`)
into the member `_components/`, stripping any operator-only columns/actions
(open-account, deposit/withdraw links) — it is a read-only list of the member's
own accounts: columns product name, available balance (`<Money>`), and a link to
`/member/savings/{id}`. `TData` extends `{ id: string }` (contract T). Keep the
`<DataTable>` wiring (in-memory adapter over the full list, like the operator
savings index).

- [ ] **Step 4: Write the list + detail pages**

```tsx
// .../savings/page.tsx
import { getMemberPageContext } from "@/auth/server-page-context";
import { MemberSavingsTable } from "./_components/MemberSavingsTable";

export default async function MemberSavingsPage() {
  const { resources } = await getMemberPageContext();
  const res = await resources.member.listSavings();
  const rows = (res.data ?? []) as Array<{ id: string }>;
  return (
    <div className="space-y-6">
      <h1 className="text-[length:var(--text-h4)] font-semibold">Your savings</h1>
      <MemberSavingsTable rows={rows as never} />
    </div>
  );
}
```

Detail page `[id]/page.tsx`: fetch the account from the list (filter by `params.id`)
+ `resources.member.getSavingsTransactions(params.id)`; render a balance card +
`MemberTransactionsTable` (clone the operator transactions table read-only:
columns date `<FormattedDate>`, type `<StatusBadge>` if applicable, amount
`<Money>`, running balance). If the id is not among the member's accounts, render
a "Not found" state (the API would 404 the transactions call — handle the error
by showing the not-found card).

- [ ] **Step 5: Run test + typecheck + lint**

Run: `cd admin && pnpm --filter @sacco/portal test -- "member/(authed)/savings" && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: PASS + clean.

- [ ] **Step 6: Commit**

```bash
git add "apps/portal/app/member/(authed)/savings"
git commit -m "feat(portal): member savings list + detail"
```

---

### Task 10: Shares list

**Files:**
- Create: `apps/portal/app/member/(authed)/shares/page.tsx`
- Create: `apps/portal/app/member/(authed)/shares/_components/MemberSharesTable.tsx`
- Test: `apps/portal/app/member/(authed)/shares/__tests__/MemberSharesTable.test.tsx`

**Interfaces:**
- Consumes: `resources.member.listShares`, `DataTable`.
- Produces: `/member/shares`.

- [ ] **Step 1: Write the failing table test**

```tsx
// .../shares/__tests__/MemberSharesTable.test.tsx
import { it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { TenantCurrencyProvider } from "@sacco/ui";
// include the same useTableUrlState mock block as the operator shares table test
import { MemberSharesTable } from "../_components/MemberSharesTable";

it("renders a row per share account", () => {
  render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <MemberSharesTable
        rows={[{ id: "s1", product_name: "Ordinary", shares_held: 120, total_value: "1200.00" } as never]}
      />
    </TenantCurrencyProvider>,
  );
  expect(screen.getByText("Ordinary")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- MemberSharesTable`
Expected: FAIL — component missing.

- [ ] **Step 3: Write MemberSharesTable + page**

Clone the operator shares accounts table (in `(tenant-authed)/shares/_components/`)
read-only: columns product name, shares held (`<Count>`), total value (`<Money>`).
Page `shares/page.tsx` mirrors the savings list page (`resources.member.listShares()`),
heading "Your shares".

- [ ] **Step 4: Run test + typecheck + lint**

Run: `cd admin && pnpm --filter @sacco/portal test -- "member/(authed)/shares" && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: PASS + clean.

- [ ] **Step 5: Commit**

```bash
git add "apps/portal/app/member/(authed)/shares"
git commit -m "feat(portal): member shares list"
```

---

### Task 11: Loans (list + detail: schedule + statement)

**Files:**
- Create: `apps/portal/app/member/(authed)/loans/page.tsx`
- Create: `apps/portal/app/member/(authed)/loans/[id]/page.tsx`
- Create: `apps/portal/app/member/(authed)/loans/_components/MemberLoansTable.tsx`
- Create: `apps/portal/app/member/(authed)/loans/[id]/_components/MemberScheduleTable.tsx`
- Create: `apps/portal/app/member/(authed)/loans/[id]/_components/MemberStatementTable.tsx`
- Test: `apps/portal/app/member/(authed)/loans/__tests__/MemberLoansTable.test.tsx`

**Interfaces:**
- Consumes: `resources.member.{listLoans,getLoan,getLoanSchedule,getLoanStatement}`, `DataTable`, `<StatusBadge entity="loan">`.
- Produces: `/member/loans` + `/member/loans/[id]`.

- [ ] **Step 1: Write the failing table test**

```tsx
// .../loans/__tests__/MemberLoansTable.test.tsx
import { it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { TenantCurrencyProvider } from "@sacco/ui";
// include the operator DataTable useTableUrlState mock block
import { MemberLoansTable } from "../_components/MemberLoansTable";

it("renders a loan row with status badge", () => {
  render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <MemberLoansTable
        rows={[{ id: "l1", loan_reference: "L-1", status: "disbursed", outstanding_principal: "1000.00" } as never]}
      />
    </TenantCurrencyProvider>,
  );
  expect(screen.getByText("L-1")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- MemberLoansTable`
Expected: FAIL — component missing.

- [ ] **Step 3: Write the loans table + page**

Clone the operator loans table (`(tenant-authed)/credit/_components/` loans list)
read-only: columns reference, `<StatusBadge entity="loan" status={...} />`,
outstanding principal (`<Money>`), link to `/member/loans/{id}`. Page
`loans/page.tsx` mirrors the savings list (`resources.member.listLoans()`),
heading "Your loans".

- [ ] **Step 4: Write the detail page (balances + schedule + statement)**

`[id]/page.tsx`: fetch `getLoan`, `getLoanSchedule`, `getLoanStatement` in
parallel; render a balances/terms card, then `MemberScheduleTable` (clone the
operator `ScheduleTable` read-only: period, due date `<FormattedDate>`, principal/
interest/total `<Money>`, status `<StatusBadge>`) and `MemberStatementTable`
(clone the operator statement table: date, description, debit/credit/running
balance `<Money>`; statement lines have no `id` → map a synthetic `id: String(i)`
for `getRowId`, exactly as the operator statement table does). **No PDF link**
(4a JSON statement only). On a 404 from `getLoan` (loan not the member's), render a
"Not found" card.

- [ ] **Step 5: Run test + typecheck + lint**

Run: `cd admin && pnpm --filter @sacco/portal test -- "member/(authed)/loans" && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint`
Expected: PASS + clean.

- [ ] **Step 6: Commit**

```bash
git add "apps/portal/app/member/(authed)/loans"
git commit -m "feat(portal): member loans list + detail (schedule + statement)"
```

---

### Task 12: Fees list + Profile + final sweep

**Files:**
- Create: `apps/portal/app/member/(authed)/fees/page.tsx`
- Create: `apps/portal/app/member/(authed)/fees/_components/MemberFeesTable.tsx`
- Create: `apps/portal/app/member/(authed)/profile/page.tsx`
- Test: `apps/portal/app/member/(authed)/fees/__tests__/MemberFeesTable.test.tsx`

**Interfaces:**
- Consumes: `resources.member.listFees`, `getMemberPageContext().member`, `DataTable`, `<StatusBadge entity="fee_assessment">`.
- Produces: `/member/fees` + `/member/profile`.

- [ ] **Step 1: Write the failing fees table test**

```tsx
// .../fees/__tests__/MemberFeesTable.test.tsx
import { it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { TenantCurrencyProvider } from "@sacco/ui";
// include the operator DataTable useTableUrlState mock block
import { MemberFeesTable } from "../_components/MemberFeesTable";

it("renders a fee row", () => {
  render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <MemberFeesTable
        rows={[{ id: "f1", amount: "10000.00", status: "assessed" } as never]}
      />
    </TenantCurrencyProvider>,
  );
  expect(screen.getByText(/assessed/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd admin && pnpm --filter @sacco/portal test -- MemberFeesTable`
Expected: FAIL — component missing.

- [ ] **Step 3: Write fees table + page + profile page**

- `MemberFeesTable`: clone the operator fee-assessments table read-only: columns
  fee type / reference, amount (`<Money>`), `<StatusBadge entity="fee_assessment" status={...} />`, assessed date (`<FormattedDate>`).
- `fees/page.tsx`: mirror the savings list (`resources.member.listFees()`), heading "Your fees".
- `profile/page.tsx`: server component using `getMemberPageContext().member`;
  render read-only cards (full name, member number, email, phone, status via
  `<StatusBadge entity="member" status={member.status} />`, date of birth, joined).
  No edit affordances.

- [ ] **Step 4: Run the full portal + ui + api-client suites**

Run:
```bash
cd admin && pnpm --filter @sacco/portal test && pnpm --filter @sacco/ui test && pnpm --filter @sacco/api-client test && pnpm --filter @sacco/portal typecheck && pnpm --filter @sacco/portal lint
```
Expected: all green; typecheck + lint clean.

- [ ] **Step 5: Commit**

```bash
git add "apps/portal/app/member/(authed)/fees" "apps/portal/app/member/(authed)/profile"
git commit -m "feat(portal): member fees list + profile"
```

---

## Final wrap-up (after Task 12)

- [ ] Update `CLAUDE.md`: append a short "Member portal (Phase 4b)" note under the portal subsection — fourth audience under `/member/*`, read-only, `member` AppShell variant, `sacco_refresh_member` cookie, `getMemberPageContext()`.
- [ ] Update memory `project_phase_4_member_auth.md` (or a new 4b note): 4b shipped, member portal live.
- [ ] Open the PR from `feat/member-portal/4b` → `main`.
- [ ] Optional manual smoke per the LOCAL STACK RUN-BOOK: bring up the stack, seed an active portal-enabled member, visit `acme.<root>/member/login` (or `?tenant=acme`), log in, click through dashboard → each section.

## Self-review notes (spec coverage)

- Same-app `/member/` segment + `(authed)` group → Tasks 6–12. ✓
- Auth: cookies/server-helpers/page-context (Task 1), route handlers (Task 2), AuthProvider/token-store/LoginForm (Task 3). ✓
- Set-password redeems operator token, token from query only → Task 6. ✓
- Middleware gating → Task 7. ✓
- AppShell member variant → Task 5. ✓
- Aggregating dashboard, no new backend endpoint → Task 8 (composes list endpoints). ✓
- Screens savings/shares/loans/fees/profile, read-only, DataTable, Money/StatusBadge → Tasks 9–12. ✓
- api-client member + memberAuth resources + queryKeys → Task 4. ✓
- Reuse existing schema read types; thin types only if shapes differ → Tasks 8–12 (verify at build). ✓
- No PDF, no mutations, bell stub, no i18n, all under `admin/` → enforced throughout. ✓
- Testing: vitest per page/component, route-handler tests, shell story → each task. ✓
