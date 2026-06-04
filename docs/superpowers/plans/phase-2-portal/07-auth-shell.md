# Portal v1 Sub-Plan 07: Auth Shell

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/portal-v1/07-auth-shell` from `main` (or rebase on top of sub-plans 01-06).

**Goal:** Ship a complete authentication shell — middleware, cookie-backed refresh, login pages, forgot/reset flows, logout, and a one-time-modal pattern. After this sub-plan merges, the portal authenticates a real user against the FastAPI backend, persists the session across reloads via an httpOnly cookie, refreshes silently on 401, redirects unauthenticated users to login, and resolves tenant context from subdomain (prod) or query+cookie (dev).

**Architecture:**
- **Refresh token in httpOnly Secure SameSite=Strict cookies** — the cookie is opaque to JS (CLAUDE.md contract C). Two cookies: `sacco_refresh_platform` (1h TTL — matches `jwt_refresh_ttl_platform_seconds`) and `sacco_refresh_tenant` (8h TTL). Different paths/contexts use different cookies so refreshes route correctly.
- **Next.js Route Handlers own the cookies.** The portal's React code never touches the refresh token. Login → `POST /api/auth/{platform,tenant}-login` → handler talks to FastAPI → sets cookie → returns access token. Refresh → `POST /api/auth/{platform,tenant}-refresh` → handler reads cookie → calls FastAPI → rotates cookie → returns new access token. Logout → handler clears cookie + calls FastAPI logout.
- **Access token lives in memory only.** Provided to the api-client via the `TokenStore` interface (sub-plan 05). Server components get a per-request store from the layout; client components share a singleton populated by a hidden `<script>` from the server.
- **Middleware** (`admin/apps/portal/middleware.ts`) resolves tenant context (subdomain → query → cookie → null), adds `x-sacco-tenant-slug` to the request headers for server components, and redirects unauthenticated GETs of protected route groups to the right login page.
- **Sub-plan 05 amendment:** `refreshMiddleware` skips its JSON body and uses `credentials: "include"` when `tokenStore.getRefreshToken()` returns `null` (cookie-backed). This change ships in Task 1 of this sub-plan.
- **Login form is shared** between platform and tenant — same Zod schema, same component. The context (`platform` | `tenant`) is a prop. Same for forgot/reset.
- **One-time modal** is reusable. Primary consumers: admin-initiated tenant-user password reset (sub-plan 32) and self-service password reset confirmation success.
- **Lockout response surfacing:** the IAM backend's lockout returns a structured 423 (Locked) or wraps a 401 with `detail` containing "lock". The login form maps it to a user-visible "Account locked — try again in N minutes" with auto-retry-after-window when the backend provides the retry-after header (sub-plan 11's form primitives will refine this).

**Tech Stack:** Next.js 15 Route Handlers, React 19, `react-hook-form` + `@hookform/resolvers/zod`, Zustand (singleton client-side store), `@sacco/api-client`, `@sacco/schemas`, `@sacco/ui`.

**Portal v1 index reference:** `docs/superpowers/plans/2026-06-02-portal-v1-index.md` §Sub-plan 07.

**Required reading:**
- Portal v1 index §3.C (cookie attributes), §3.F (one-time modal), §7.5 (login flows), §7.9 (one-time modal)
- `app/modules/iam/platform_auth/api.py` and `app/modules/iam/tenant_auth/api.py` (request/response shapes)
- CLAUDE.md "IAM module contracts" (token TTLs, anti-enumeration, lockout, session revocation)
- Sub-plan 05's `client.ts` middleware order so we don't break it

**Prerequisite:** **Sub-plans 03, 04, 05, 06 must be merged** (or rebased onto). This sub-plan consumes all four.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `admin/apps/portal/package.json` | Modify | Add `zustand`, `react-hook-form`, `@hookform/resolvers` |
| `admin/apps/portal/src/auth/cookies.ts` | Create | Cookie helpers (read/set/clear with attribute defaults) |
| `admin/apps/portal/src/auth/token-store.ts` | Create | Client-side singleton `CookieBackedTokenStore` |
| `admin/apps/portal/src/auth/tenant-resolver.ts` | Create | Subdomain → query → cookie tenant resolution |
| `admin/apps/portal/src/auth/server-helpers.ts` | Create | `getServerAccessToken()`, `getServerTenantSlug()` for RSC |
| `admin/apps/portal/middleware.ts` | Create | Tenant resolution + auth redirect |
| `admin/apps/portal/app/api/auth/platform-login/route.ts` | Create | POST handler |
| `admin/apps/portal/app/api/auth/tenant-login/route.ts` | Create | POST handler |
| `admin/apps/portal/app/api/auth/platform-refresh/route.ts` | Create | POST handler |
| `admin/apps/portal/app/api/auth/tenant-refresh/route.ts` | Create | POST handler |
| `admin/apps/portal/app/api/auth/platform-logout/route.ts` | Create | POST handler |
| `admin/apps/portal/app/api/auth/tenant-logout/route.ts` | Create | POST handler |
| `admin/apps/portal/src/auth/AuthProvider.tsx` | Create | React context wrapping the api-client + token store |
| `admin/apps/portal/src/auth/use-auth.ts` | Create | `useAuth()` hook |
| `admin/apps/portal/src/components/forms/LoginForm.tsx` | Create | Shared login form |
| `admin/apps/portal/src/components/forms/ForgotPasswordForm.tsx` | Create | Shared forgot form |
| `admin/apps/portal/src/components/forms/ResetPasswordForm.tsx` | Create | Shared reset form |
| `admin/apps/portal/src/components/OneTimeModal.tsx` | Create | Reusable single-view modal |
| `admin/apps/portal/app/platform/login/page.tsx` | Create | Platform login screen |
| `admin/apps/portal/app/platform/forgot-password/page.tsx` | Create | Platform forgot screen |
| `admin/apps/portal/app/platform/reset-password/page.tsx` | Create | Platform reset screen |
| `admin/apps/portal/app/(tenant)/login/page.tsx` | Create | Tenant login screen |
| `admin/apps/portal/app/(tenant)/forgot-password/page.tsx` | Create | Tenant forgot screen |
| `admin/apps/portal/app/(tenant)/reset-password/page.tsx` | Create | Tenant reset screen |
| `admin/apps/portal/app/layout.tsx` | Modify | Wrap children in `<AuthProvider>` |
| `admin/packages/api-client/src/middleware/refresh.ts` | Modify | Cookie-backed refresh path (skip body when refreshToken is null) |
| `admin/packages/api-client/src/__tests__/middleware.test.ts` | Modify | Cover the cookie-backed branch |
| `admin/apps/portal/src/auth/__tests__/*.test.tsx` | Create | RTL + MSW coverage |
| `admin/apps/portal/tests/e2e/auth.spec.ts` | Create | Playwright login → me → logout |
| `admin/apps/portal/playwright.config.ts` | Create | Playwright runner config |

---

## Task 1: Sub-plan 05 amendment — cookie-backed refresh

**Files:**
- Modify: `admin/packages/api-client/src/middleware/refresh.ts`
- Modify: `admin/packages/api-client/src/__tests__/middleware.test.ts`

- [ ] **Step 1: Update `refreshMiddleware`**

Replace the body of `refreshMiddleware` so it has two paths:

```typescript
// admin/packages/api-client/src/middleware/refresh.ts
import type { Middleware } from "openapi-fetch";
import type { TokenStore } from "../token-store";
import { UnauthorizedError } from "../errors";

export function refreshMiddleware(
  tokenStore: TokenStore,
  baseUrl: string,
): Middleware {
  let pending: Promise<string | null> | null = null;

  async function refreshOnce(): Promise<string | null> {
    if (pending) return pending;
    pending = (async () => {
      try {
        const refreshToken = tokenStore.getRefreshToken();
        const endpoint = `${baseUrl}${tokenStore.getRefreshEndpoint()}`;
        // Cookie-backed branch (Next.js auth shell, sub-plan 07): refresh
        // token lives in an httpOnly cookie. Send no body; rely on
        // credentials: "include" so the cookie attaches automatically.
        const r =
          refreshToken === null
            ? await fetch(endpoint, {
                method: "POST",
                credentials: "include",
              })
            : await fetch(endpoint, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ refresh_token: refreshToken }),
                credentials: "include",
              });
        if (!r.ok) return null;
        const data = (await r.json()) as { access_token?: string };
        const token = data.access_token ?? null;
        tokenStore.setAccessToken(token);
        return token;
      } finally {
        pending = null;
      }
    })();
    return pending;
  }

  return {
    async onResponse({ request, response }) {
      if (response.status !== 401) return response;
      if (request.headers.get("X-Sacco-Retry") === "1") {
        throw new UnauthorizedError();
      }
      const newToken = await refreshOnce();
      if (!newToken) {
        throw new UnauthorizedError();
      }
      const retry = new Request(request, {
        headers: new Headers(request.headers),
      });
      retry.headers.set("Authorization", `Bearer ${newToken}`);
      retry.headers.set("X-Sacco-Retry", "1");
      return fetch(retry);
    },
  };
}
```

- [ ] **Step 2: Add a test case for the cookie-backed branch**

In `admin/packages/api-client/src/__tests__/middleware.test.ts`, append:

```typescript
describe("refreshMiddleware (cookie-backed)", () => {
  it("uses credentials:include with no body when refresh token is null", async () => {
    // The MSW handler ignores the body — it just checks for the Cookie
    // header (which the test runner doesn't forward, so we accept any
    // request and respond with a fresh token).
    server.use(
      http.post(`${BASE}/api/auth/platform-refresh`, () =>
        HttpResponse.json({
          access_token: "fresh-from-cookie",
          expires_in: 900,
        }),
      ),
      http.get(`${BASE}/platform/auth/me`, ({ request }) =>
        request.headers.get("Authorization") === "Bearer fresh-from-cookie"
          ? HttpResponse.json({ id: "p2" })
          : new HttpResponse(null, { status: 401 }),
      ),
    );
    const store = new InMemoryTokenStore("/api/auth/platform-refresh");
    store.setAccessToken("stale-token");
    // Cookie-backed: no refresh token in JS.
    store.setRefreshToken(null);
    const api = createApiClient({
      baseUrl: BASE,
      tokenStore: store,
      tenantContext: new FixedTenantContext(null),
    });
    const { data } = await api.GET("/platform/auth/me" as never);
    expect(data).toEqual({ id: "p2" });
    expect(store.getAccessToken()).toBe("fresh-from-cookie");
  });
});
```

- [ ] **Step 3: Verify the api-client tests still pass**

```bash
cd admin
pnpm --filter @sacco/api-client test
```
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add admin/packages/api-client/src/middleware/refresh.ts \
        admin/packages/api-client/src/__tests__/middleware.test.ts
git commit -m "feat(api-client): cookie-backed refresh path (no body when refresh token is null)"
```

---

## Task 2: Cookie helpers + token store + tenant resolver

**Files:**
- Modify: `admin/apps/portal/package.json` (add deps)
- Create: `admin/apps/portal/src/auth/cookies.ts`
- Create: `admin/apps/portal/src/auth/token-store.ts`
- Create: `admin/apps/portal/src/auth/tenant-resolver.ts`
- Create: `admin/apps/portal/src/auth/server-helpers.ts`

- [ ] **Step 1: Add runtime deps to the portal**

In `admin/apps/portal/package.json`, append to `dependencies`:

```json
"@sacco/api-client": "workspace:*",
"@sacco/schemas": "workspace:*",
"@sacco/ui": "workspace:*",
"@hookform/resolvers": "^3.9.0",
"react-hook-form": "^7.53.0",
"zod": "^3.23.8",
"zustand": "^4.5.5"
```

Append to `devDependencies`:

```json
"@playwright/test": "^1.47.0"
```

Install:

```bash
make admin-install
```

- [ ] **Step 2: Cookie helpers (Route Handler side)**

```typescript
// admin/apps/portal/src/auth/cookies.ts
import { cookies } from "next/headers";

export const PLATFORM_REFRESH_COOKIE = "sacco_refresh_platform";
export const TENANT_REFRESH_COOKIE = "sacco_refresh_tenant";
export const TENANT_SLUG_COOKIE = "sacco_tenant_slug";

const isProd = process.env.NODE_ENV === "production";

export const PLATFORM_REFRESH_MAX_AGE = 60 * 60; // 1 hour
export const TENANT_REFRESH_MAX_AGE = 60 * 60 * 8; // 8 hours

interface SetRefreshArgs {
  name: typeof PLATFORM_REFRESH_COOKIE | typeof TENANT_REFRESH_COOKIE;
  value: string;
  maxAgeSeconds: number;
}

export async function setRefreshCookie(args: SetRefreshArgs): Promise<void> {
  const jar = await cookies();
  jar.set({
    name: args.name,
    value: args.value,
    httpOnly: true,
    secure: isProd,
    sameSite: "strict",
    path: "/",
    maxAge: args.maxAgeSeconds,
  });
}

export async function clearRefreshCookie(
  name: typeof PLATFORM_REFRESH_COOKIE | typeof TENANT_REFRESH_COOKIE,
): Promise<void> {
  const jar = await cookies();
  jar.delete(name);
}

export async function readRefreshCookie(
  name: typeof PLATFORM_REFRESH_COOKIE | typeof TENANT_REFRESH_COOKIE,
): Promise<string | null> {
  const jar = await cookies();
  return jar.get(name)?.value ?? null;
}

export async function setTenantSlugCookie(slug: string): Promise<void> {
  const jar = await cookies();
  jar.set({
    name: TENANT_SLUG_COOKIE,
    value: slug,
    httpOnly: false, // readable by middleware AND client for the tenant indicator
    secure: isProd,
    sameSite: "strict",
    path: "/",
    maxAge: 60 * 60 * 24 * 30, // 30 days
  });
}
```

- [ ] **Step 3: Tenant resolver**

```typescript
// admin/apps/portal/src/auth/tenant-resolver.ts
// Resolves the active tenant slug for a request. Used by middleware AND
// by server-side helpers.
//
// Order of precedence (highest first):
//   1. Production: subdomain (e.g., sacco-one.app.sacco.example → "sacco-one")
//   2. Dev:        ?tenant=<slug> query param
//   3. Both:       sacco_tenant_slug cookie
//   4. null        (treat as platform-only context)
//
// The slug matches the backend's [a-z0-9-]{1,40} pattern.

const SLUG_RE = /^[a-z0-9-]{1,40}$/;

interface ResolveArgs {
  host: string | null;
  searchParams: URLSearchParams;
  cookieValue: string | null;
  rootDomain?: string; // e.g., "app.sacco.example"
}

export function resolveTenantSlug(args: ResolveArgs): string | null {
  // Subdomain in production
  if (args.host && args.rootDomain) {
    const subdomain = extractSubdomain(args.host, args.rootDomain);
    if (subdomain && SLUG_RE.test(subdomain)) return subdomain;
  }
  // Query param for dev
  const queryParam = args.searchParams.get("tenant");
  if (queryParam && SLUG_RE.test(queryParam)) return queryParam;
  // Cookie persistence
  if (args.cookieValue && SLUG_RE.test(args.cookieValue)) {
    return args.cookieValue;
  }
  return null;
}

function extractSubdomain(host: string, rootDomain: string): string | null {
  const hostNoPort = host.split(":")[0]?.toLowerCase() ?? "";
  const root = rootDomain.toLowerCase();
  if (hostNoPort === root || !hostNoPort.endsWith(`.${root}`)) return null;
  const sub = hostNoPort.slice(0, -1 - root.length);
  // Reject "www" and any nested-subdomain leftover dots.
  if (!sub || sub === "www" || sub.includes(".")) return null;
  return sub;
}
```

- [ ] **Step 4: Client-side token store + tenant context (singleton)**

```typescript
// admin/apps/portal/src/auth/token-store.ts
"use client";

import type { TenantContext, TokenStore } from "@sacco/api-client";
import { create } from "zustand";

interface AuthState {
  accessToken: string | null;
  tenantSlug: string | null;
  authContext: "platform" | "tenant";
  setAccessToken(token: string | null): void;
  setTenantSlug(slug: string | null): void;
  setAuthContext(ctx: "platform" | "tenant"): void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  tenantSlug: null,
  authContext: "platform",
  setAccessToken: (token) => set({ accessToken: token }),
  setTenantSlug: (slug) => set({ tenantSlug: slug }),
  setAuthContext: (ctx) => set({ authContext: ctx }),
}));

export class CookieBackedTokenStore implements TokenStore {
  getAccessToken(): string | null {
    return useAuthStore.getState().accessToken;
  }
  setAccessToken(token: string | null): void {
    useAuthStore.getState().setAccessToken(token);
  }
  getRefreshEndpoint(): "/api/auth/platform-refresh" | "/api/auth/tenant-refresh" {
    const ctx = useAuthStore.getState().authContext;
    return ctx === "platform"
      ? "/api/auth/platform-refresh"
      : ("/api/auth/tenant-refresh" as never);
  }
  /**
   * Always returns null — refresh token lives in an httpOnly cookie. The
   * api-client's refresh middleware (sub-plan 05, amended in Task 1)
   * sees null and uses credentials:include with no body.
   */
  getRefreshToken(): null {
    return null;
  }
}

export class ClientTenantContext implements TenantContext {
  getSlug(): string | null {
    return useAuthStore.getState().tenantSlug;
  }
}
```

- [ ] **Step 5: Server-helper for RSC**

```typescript
// admin/apps/portal/src/auth/server-helpers.ts
// Server-side helpers that read auth state from Next.js headers (set by
// middleware) and cookies. Used by server components to construct a
// per-request api-client.

import { headers } from "next/headers";

const HEADER_TENANT_SLUG = "x-sacco-tenant-slug";
const HEADER_ACCESS_TOKEN = "x-sacco-access-token";

export async function getServerTenantSlug(): Promise<string | null> {
  const h = await headers();
  return h.get(HEADER_TENANT_SLUG);
}

/**
 * The middleware does not mint access tokens — it forwards an existing
 * access token from a (short-lived, in-memory) cache. Server components
 * that need to issue authenticated calls must either:
 *   (a) read the access token from a per-request header set by the
 *       auth shell layout (sub-plan 08), or
 *   (b) call the refresh route handler to get a fresh token.
 *
 * Production wiring lands in sub-plan 08. For now, this helper returns
 * null and server-component calls fall back to the public surface.
 */
export async function getServerAccessToken(): Promise<string | null> {
  const h = await headers();
  return h.get(HEADER_ACCESS_TOKEN);
}
```

- [ ] **Step 6: Commit**

```bash
git add admin/apps/portal/package.json \
        admin/apps/portal/src/auth/ \
        admin/pnpm-lock.yaml
git commit -m "feat(portal): cookie helpers + CookieBackedTokenStore + tenant resolver"
```

---

## Task 3: Route Handlers — login, refresh, logout (platform + tenant)

**Files:**
- Create: `admin/apps/portal/app/api/auth/platform-login/route.ts`
- Create: `admin/apps/portal/app/api/auth/tenant-login/route.ts`
- Create: `admin/apps/portal/app/api/auth/platform-refresh/route.ts`
- Create: `admin/apps/portal/app/api/auth/tenant-refresh/route.ts`
- Create: `admin/apps/portal/app/api/auth/platform-logout/route.ts`
- Create: `admin/apps/portal/app/api/auth/tenant-logout/route.ts`

- [ ] **Step 1: Platform login**

```typescript
// admin/apps/portal/app/api/auth/platform-login/route.ts
import { NextResponse } from "next/server";
import { loginSchema } from "@sacco/schemas";
import {
  PLATFORM_REFRESH_COOKIE,
  PLATFORM_REFRESH_MAX_AGE,
  setRefreshCookie,
} from "@/auth/cookies";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.json();
  const parsed = loginSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid request", issues: parsed.error.format() },
      { status: 400 },
    );
  }

  const r = await fetch(`${API_BASE}/platform/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(parsed.data),
  });
  if (!r.ok) {
    const detail = await safeJson(r);
    return NextResponse.json(detail ?? { error: "Login failed" }, {
      status: r.status,
    });
  }
  const data = (await r.json()) as {
    access_token: string;
    refresh_token: string;
    expires_in: number;
  };

  await setRefreshCookie({
    name: PLATFORM_REFRESH_COOKIE,
    value: data.refresh_token,
    maxAgeSeconds: PLATFORM_REFRESH_MAX_AGE,
  });

  // Return the access token + expiry to the client; never the refresh token.
  return NextResponse.json({
    access_token: data.access_token,
    expires_in: data.expires_in,
  });
}

async function safeJson(r: Response): Promise<unknown> {
  try {
    return await r.json();
  } catch {
    return null;
  }
}
```

- [ ] **Step 2: Tenant login**

```typescript
// admin/apps/portal/app/api/auth/tenant-login/route.ts
import { NextResponse } from "next/server";
import { loginSchema } from "@sacco/schemas";
import {
  TENANT_REFRESH_COOKIE,
  TENANT_REFRESH_MAX_AGE,
  setRefreshCookie,
  setTenantSlugCookie,
} from "@/auth/cookies";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.json();
  const parsed = loginSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid request", issues: parsed.error.format() },
      { status: 400 },
    );
  }

  const tenantSlug = request.headers.get("x-sacco-tenant-slug");
  if (!tenantSlug) {
    return NextResponse.json(
      { error: "Tenant context missing" },
      { status: 400 },
    );
  }

  const r = await fetch(`${API_BASE}/auth/token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-Slug": tenantSlug,
    },
    body: JSON.stringify(parsed.data),
  });
  if (!r.ok) {
    const detail = await safeJson(r);
    return NextResponse.json(detail ?? { error: "Login failed" }, {
      status: r.status,
    });
  }
  const data = (await r.json()) as {
    access_token: string;
    refresh_token: string;
    expires_in: number;
  };

  await setRefreshCookie({
    name: TENANT_REFRESH_COOKIE,
    value: data.refresh_token,
    maxAgeSeconds: TENANT_REFRESH_MAX_AGE,
  });
  // Persist the slug so reloads keep tenant context without a query param.
  await setTenantSlugCookie(tenantSlug);

  return NextResponse.json({
    access_token: data.access_token,
    expires_in: data.expires_in,
    tenant_slug: tenantSlug,
  });
}

async function safeJson(r: Response): Promise<unknown> {
  try {
    return await r.json();
  } catch {
    return null;
  }
}
```

- [ ] **Step 3: Platform refresh + tenant refresh**

Both follow the same shape: read cookie, call backend, rotate cookie, return access token.

```typescript
// admin/apps/portal/app/api/auth/platform-refresh/route.ts
import { NextResponse } from "next/server";
import {
  PLATFORM_REFRESH_COOKIE,
  PLATFORM_REFRESH_MAX_AGE,
  readRefreshCookie,
  setRefreshCookie,
} from "@/auth/cookies";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export async function POST(): Promise<NextResponse> {
  const refreshToken = await readRefreshCookie(PLATFORM_REFRESH_COOKIE);
  if (!refreshToken) {
    return NextResponse.json({ error: "No refresh token" }, { status: 401 });
  }
  const r = await fetch(`${API_BASE}/platform/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!r.ok) {
    return NextResponse.json({ error: "Refresh failed" }, { status: 401 });
  }
  const data = (await r.json()) as {
    access_token: string;
    refresh_token: string;
    expires_in: number;
  };
  await setRefreshCookie({
    name: PLATFORM_REFRESH_COOKIE,
    value: data.refresh_token,
    maxAgeSeconds: PLATFORM_REFRESH_MAX_AGE,
  });
  return NextResponse.json({
    access_token: data.access_token,
    expires_in: data.expires_in,
  });
}
```

```typescript
// admin/apps/portal/app/api/auth/tenant-refresh/route.ts
import { NextResponse } from "next/server";
import {
  TENANT_REFRESH_COOKIE,
  TENANT_REFRESH_MAX_AGE,
  readRefreshCookie,
  setRefreshCookie,
} from "@/auth/cookies";
import { cookies } from "next/headers";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export async function POST(): Promise<NextResponse> {
  const refreshToken = await readRefreshCookie(TENANT_REFRESH_COOKIE);
  if (!refreshToken) {
    return NextResponse.json({ error: "No refresh token" }, { status: 401 });
  }
  // Tenant refresh needs the slug — read it from the persistence cookie.
  const jar = await cookies();
  const slug = jar.get("sacco_tenant_slug")?.value;
  if (!slug) {
    return NextResponse.json({ error: "Tenant context missing" }, { status: 401 });
  }
  const r = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-Slug": slug,
    },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!r.ok) {
    return NextResponse.json({ error: "Refresh failed" }, { status: 401 });
  }
  const data = (await r.json()) as {
    access_token: string;
    refresh_token: string;
    expires_in: number;
  };
  await setRefreshCookie({
    name: TENANT_REFRESH_COOKIE,
    value: data.refresh_token,
    maxAgeSeconds: TENANT_REFRESH_MAX_AGE,
  });
  return NextResponse.json({
    access_token: data.access_token,
    expires_in: data.expires_in,
  });
}
```

- [ ] **Step 4: Logout handlers**

```typescript
// admin/apps/portal/app/api/auth/platform-logout/route.ts
import { NextResponse } from "next/server";
import {
  PLATFORM_REFRESH_COOKIE,
  clearRefreshCookie,
  readRefreshCookie,
} from "@/auth/cookies";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export async function POST(request: Request): Promise<NextResponse> {
  // Best-effort: call backend logout if we have a Bearer header.
  const auth = request.headers.get("authorization");
  if (auth) {
    void fetch(`${API_BASE}/platform/auth/logout`, {
      method: "POST",
      headers: { Authorization: auth },
    });
  }
  // Always clear our cookie even if the backend call fails.
  await clearRefreshCookie(PLATFORM_REFRESH_COOKIE);
  return NextResponse.json({ status: "ok" });
}
```

(Tenant logout is structurally identical — clears `TENANT_REFRESH_COOKIE` and calls `/auth/logout`. Use the platform version as a template.)

- [ ] **Step 5: Commit**

```bash
git add admin/apps/portal/app/api/auth/
git commit -m "feat(portal): Route Handlers for login/refresh/logout (platform + tenant)"
```

---

## Task 4: Next.js middleware

**Files:**
- Create: `admin/apps/portal/middleware.ts`

- [ ] **Step 1: Write the middleware**

```typescript
// admin/apps/portal/middleware.ts
// Runs before every page request. Resolves tenant slug, propagates it to
// downstream server components via header, and redirects unauthenticated
// GETs of protected pages to the right login.

import { NextResponse, type NextRequest } from "next/server";
import { resolveTenantSlug } from "@/auth/tenant-resolver";

const PUBLIC_PATHS_PLATFORM = new Set([
  "/platform/login",
  "/platform/forgot-password",
  "/platform/reset-password",
]);
const PUBLIC_PATHS_TENANT = new Set([
  "/login",
  "/forgot-password",
  "/reset-password",
]);

const PLATFORM_REFRESH_COOKIE = "sacco_refresh_platform";
const TENANT_REFRESH_COOKIE = "sacco_refresh_tenant";
const TENANT_SLUG_COOKIE = "sacco_tenant_slug";

const ROOT_DOMAIN = process.env.NEXT_PUBLIC_ROOT_DOMAIN ?? "";

export const config = {
  // Run on every request except Next.js internals and static assets.
  matcher: ["/((?!api|_next/static|_next/image|favicon|public).*)"],
};

export function middleware(request: NextRequest): NextResponse {
  const url = request.nextUrl;
  const pathname = url.pathname;

  const isPlatformPath = pathname.startsWith("/platform");

  // 1. Resolve tenant slug
  const slug = resolveTenantSlug({
    host: request.headers.get("host"),
    searchParams: url.searchParams,
    cookieValue: request.cookies.get(TENANT_SLUG_COOKIE)?.value ?? null,
    rootDomain: ROOT_DOMAIN,
  });

  // 2. Build request headers for downstream RSC consumption
  const headers = new Headers(request.headers);
  if (slug) headers.set("x-sacco-tenant-slug", slug);

  // 3. Authentication redirect
  const isPublic = isPlatformPath
    ? PUBLIC_PATHS_PLATFORM.has(pathname)
    : PUBLIC_PATHS_TENANT.has(pathname);

  if (!isPublic) {
    const hasRefresh = isPlatformPath
      ? request.cookies.has(PLATFORM_REFRESH_COOKIE)
      : request.cookies.has(TENANT_REFRESH_COOKIE);
    if (!hasRefresh) {
      const loginPath = isPlatformPath ? "/platform/login" : "/login";
      const redirect = new URL(loginPath, request.url);
      redirect.searchParams.set("next", pathname);
      return NextResponse.redirect(redirect);
    }
  }

  // 4. Persist tenant slug cookie on first-load query-param resolution (dev)
  const response = NextResponse.next({
    request: { headers },
  });
  if (slug && !request.cookies.has(TENANT_SLUG_COOKIE) && !isPlatformPath) {
    response.cookies.set({
      name: TENANT_SLUG_COOKIE,
      value: slug,
      httpOnly: false,
      secure: process.env.NODE_ENV === "production",
      sameSite: "strict",
      path: "/",
      maxAge: 60 * 60 * 24 * 30,
    });
  }
  return response;
}
```

- [ ] **Step 2: Update path-alias in `tsconfig.json`**

Open `admin/apps/portal/tsconfig.json`. Ensure `compilerOptions` includes `paths` so `@/...` resolves:

```json
{
  "compilerOptions": {
    "baseUrl": "./",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add admin/apps/portal/middleware.ts \
        admin/apps/portal/tsconfig.json
git commit -m "feat(portal): middleware (tenant resolution + auth redirect)"
```

---

## Task 5: AuthProvider + useAuth hook

**Files:**
- Create: `admin/apps/portal/src/auth/AuthProvider.tsx`
- Create: `admin/apps/portal/src/auth/use-auth.ts`
- Modify: `admin/apps/portal/app/layout.tsx`

- [ ] **Step 1: AuthProvider**

```tsx
// admin/apps/portal/src/auth/AuthProvider.tsx
"use client";

import {
  buildResources,
  createApiClient,
  type FetchClient,
  type Resources,
} from "@sacco/api-client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { CookieBackedTokenStore, ClientTenantContext, useAuthStore } from "./token-store";

interface AuthContextValue {
  api: FetchClient;
  resources: Resources;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

interface AuthProviderProps {
  children: ReactNode;
  baseUrl: string;
  initialAccessToken?: string | null;
  initialTenantSlug?: string | null;
  initialAuthContext?: "platform" | "tenant";
}

export function AuthProvider({
  children,
  baseUrl,
  initialAccessToken,
  initialTenantSlug,
  initialAuthContext,
}: AuthProviderProps) {
  // Hydrate the zustand store once from server-provided values
  useEffect(() => {
    const store = useAuthStore.getState();
    if (initialAccessToken !== undefined) store.setAccessToken(initialAccessToken);
    if (initialTenantSlug !== undefined) store.setTenantSlug(initialTenantSlug);
    if (initialAuthContext) store.setAuthContext(initialAuthContext);
    // Intentionally no dep array — only run once at mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: (failureCount, error) => {
              // Never auto-retry on auth failure
              if (error instanceof Error && error.name === "UnauthorizedError") return false;
              return failureCount < 2;
            },
          },
        },
      }),
  );

  const value = useMemo<AuthContextValue>(() => {
    const api = createApiClient({
      baseUrl,
      tokenStore: new CookieBackedTokenStore(),
      tenantContext: new ClientTenantContext(),
    });
    return { api, resources: buildResources(api) };
  }, [baseUrl]);

  return (
    <AuthContext.Provider value={value}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </AuthContext.Provider>
  );
}
```

- [ ] **Step 2: useAuth hook**

```typescript
// admin/apps/portal/src/auth/use-auth.ts
"use client";

import { useContext } from "react";
import { AuthContext } from "./AuthProvider";
import { useAuthStore } from "./token-store";

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  const accessToken = useAuthStore((s) => s.accessToken);
  const tenantSlug = useAuthStore((s) => s.tenantSlug);
  const authContext = useAuthStore((s) => s.authContext);
  return {
    ...ctx,
    accessToken,
    tenantSlug,
    authContext,
    isAuthenticated: accessToken !== null,
  };
}
```

- [ ] **Step 3: Wrap the app layout in `<AuthProvider>`**

Update `admin/apps/portal/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";

import "./globals.css";
import { AuthProvider } from "@/auth/AuthProvider";
import { getServerTenantSlug } from "@/auth/server-helpers";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "SACCO Admin Portal",
  description: "Operational back-office for the SACCO platform",
  robots: { index: false, follow: false },
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const tenantSlug = await getServerTenantSlug();
  const initialAuthContext = tenantSlug ? "tenant" : "platform";
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <AuthProvider
          baseUrl={API_BASE}
          initialTenantSlug={tenantSlug}
          initialAuthContext={initialAuthContext}
        >
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add admin/apps/portal/src/auth/AuthProvider.tsx \
        admin/apps/portal/src/auth/use-auth.ts \
        admin/apps/portal/app/layout.tsx
git commit -m "feat(portal): AuthProvider + useAuth hook + layout wiring"
```

---

## Task 6: Login form + login pages

**Files:**
- Create: `admin/apps/portal/src/components/forms/LoginForm.tsx`
- Create: `admin/apps/portal/app/platform/login/page.tsx`
- Create: `admin/apps/portal/app/(tenant)/login/page.tsx`

- [ ] **Step 1: Login form**

```tsx
// admin/apps/portal/src/components/forms/LoginForm.tsx
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { loginSchema, type LoginInput } from "@sacco/schemas";
import { Button, Input, Label, Card } from "@sacco/ui";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useAuthStore } from "@/auth/token-store";

type Variant = "platform" | "tenant";

interface LoginFormProps {
  variant: Variant;
}

export function LoginForm({ variant }: LoginFormProps) {
  const router = useRouter();
  const params = useSearchParams();
  const setAccessToken = useAuthStore((s) => s.setAccessToken);
  const setAuthContext = useAuthStore((s) => s.setAuthContext);
  const setTenantSlug = useAuthStore((s) => s.setTenantSlug);
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  const endpoint =
    variant === "platform"
      ? "/api/auth/platform-login"
      : "/api/auth/tenant-login";

  async function onSubmit(values: LoginInput) {
    setServerError(null);
    const r = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
      credentials: "include",
    });
    if (!r.ok) {
      const detail = await r.json().catch(() => ({}));
      if (r.status === 423 || (typeof detail?.detail === "string" && detail.detail.toLowerCase().includes("lock"))) {
        setServerError("Account locked — please try again in 30 minutes.");
      } else if (r.status === 401) {
        setServerError("Invalid email or password.");
      } else {
        setServerError(detail?.detail ?? "Login failed. Please try again.");
      }
      return;
    }
    const data = (await r.json()) as {
      access_token: string;
      tenant_slug?: string;
    };
    setAccessToken(data.access_token);
    setAuthContext(variant);
    if (variant === "tenant" && data.tenant_slug) {
      setTenantSlug(data.tenant_slug);
    }
    const next = params.get("next");
    router.push(next ?? (variant === "platform" ? "/platform" : "/"));
  }

  return (
    <Card className="max-w-md p-8">
      <h1 className="mb-1 text-[var(--text-h3)] font-semibold text-[var(--text-primary)]">
        {variant === "platform" ? "Platform sign in" : "Sign in"}
      </h1>
      <p className="mb-6 text-[var(--text-body)] text-[var(--text-secondary)]">
        {variant === "platform"
          ? "Sign in to operate the SACCO platform."
          : "Sign in to your SACCO."}
      </p>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
        <div>
          <Label htmlFor="email" required>
            Email
          </Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            error={Boolean(errors.email)}
            {...register("email")}
          />
          {errors.email && (
            <p className="mt-1 text-xs text-[var(--text-danger)]">
              {errors.email.message}
            </p>
          )}
        </div>
        <div>
          <Label htmlFor="password" required>
            Password
          </Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            error={Boolean(errors.password)}
            {...register("password")}
          />
          {errors.password && (
            <p className="mt-1 text-xs text-[var(--text-danger)]">
              {errors.password.message}
            </p>
          )}
        </div>
        {serverError && (
          <p
            role="alert"
            className="rounded-md bg-[var(--status-danger-bg)] p-3 text-sm text-[var(--text-danger)]"
          >
            {serverError}
          </p>
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Signing in…" : "Sign in"}
        </Button>
        <p className="text-center text-sm">
          <a
            href={
              variant === "platform"
                ? "/platform/forgot-password"
                : "/forgot-password"
            }
            className="text-[var(--text-link)] hover:underline"
          >
            Forgot password?
          </a>
        </p>
      </form>
    </Card>
  );
}
```

- [ ] **Step 2: Pages**

```tsx
// admin/apps/portal/app/platform/login/page.tsx
import { LoginForm } from "@/components/forms/LoginForm";

export default function PlatformLogin() {
  return (
    <main className="mx-auto grid min-h-screen max-w-3xl place-items-center p-8">
      <LoginForm variant="platform" />
    </main>
  );
}
```

```tsx
// admin/apps/portal/app/(tenant)/login/page.tsx
import { LoginForm } from "@/components/forms/LoginForm";

export default function TenantLogin() {
  return (
    <main className="mx-auto grid min-h-screen max-w-3xl place-items-center p-8">
      <LoginForm variant="tenant" />
    </main>
  );
}
```

- [ ] **Step 3: Verify dev server + visual smoke**

```bash
make admin-dev &
DEV_PID=$!
sleep 8
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/platform/login
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/login
kill $DEV_PID 2>/dev/null || true
```
Expected: both return 200.

Manual visual check: navigate to `http://localhost:3000/platform/login` and verify the form renders with token-styled colours.

- [ ] **Step 4: Commit**

```bash
git add admin/apps/portal/src/components/forms/LoginForm.tsx \
        admin/apps/portal/app/platform/login/ \
        admin/apps/portal/app/\(tenant\)/login/
git commit -m "feat(portal): shared LoginForm + platform + tenant login pages"
```

---

## Task 7: Forgot + reset password (with one-time modal)

**Files:**
- Create: `admin/apps/portal/src/components/OneTimeModal.tsx`
- Create: `admin/apps/portal/src/components/forms/ForgotPasswordForm.tsx`
- Create: `admin/apps/portal/src/components/forms/ResetPasswordForm.tsx`
- Create: `admin/apps/portal/app/platform/forgot-password/page.tsx`
- Create: `admin/apps/portal/app/platform/reset-password/page.tsx`
- Create: `admin/apps/portal/app/(tenant)/forgot-password/page.tsx`
- Create: `admin/apps/portal/app/(tenant)/reset-password/page.tsx`

- [ ] **Step 1: OneTimeModal**

```tsx
// admin/apps/portal/src/components/OneTimeModal.tsx
"use client";

import {
  Button,
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@sacco/ui";
import { Copy, Check } from "lucide-react";
import { useState, type ReactNode } from "react";

interface OneTimeModalProps {
  open: boolean;
  onAcknowledge(): void;
  title: string;
  description: string;
  payload: string;
  payloadLabel?: string;
  warningCopy?: ReactNode;
}

/**
 * Single-view "this won't be shown again" modal. Used for:
 *  - Self-service password reset success (token displayed once)
 *  - Admin-initiated tenant-user password reset (sub-plan 32)
 *
 * Forces the user to acknowledge before the modal closes. Provides a
 * one-click copy with a 2s feedback state. Closing fires onAcknowledge —
 * there is no "X" close button and no overlay-click dismissal.
 */
export function OneTimeModal({
  open,
  onAcknowledge,
  title,
  description,
  payload,
  payloadLabel = "Token",
  warningCopy,
}: OneTimeModalProps) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(payload);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }
  return (
    <Dialog open={open}>
      <DialogContent
        onPointerDownOutside={(e) => e.preventDefault()}
        onEscapeKeyDown={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <DialogBody>
          <p className="mb-4 text-[var(--text-secondary)]">{description}</p>
          {warningCopy && (
            <p className="mb-4 rounded-md bg-[var(--status-warning-bg)] p-3 text-[var(--text-warning)]">
              {warningCopy}
            </p>
          )}
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
              {payloadLabel}
            </p>
            <div className="flex items-center gap-2 rounded-md border border-[var(--border-default)] bg-[var(--surface-sunken)] p-3">
              <code className="flex-1 break-all font-mono text-sm">{payload}</code>
              <Button variant="secondary" size="sm" onClick={copy} type="button">
                {copied ? <Check size={16} /> : <Copy size={16} />}
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
          </div>
        </DialogBody>
        <DialogFooter>
          <Button onClick={onAcknowledge}>
            I've recorded this and won't need it shown again
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: ForgotPasswordForm**

```tsx
// admin/apps/portal/src/components/forms/ForgotPasswordForm.tsx
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  passwordResetRequestSchema,
  type PasswordResetRequestInput,
} from "@sacco/schemas";
import { Button, Card, Input, Label } from "@sacco/ui";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";

type Variant = "platform" | "tenant";

interface Props {
  variant: Variant;
}

export function ForgotPasswordForm({ variant }: Props) {
  const [submitted, setSubmitted] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<PasswordResetRequestInput>({
    resolver: zodResolver(passwordResetRequestSchema),
    defaultValues: { email: "" },
  });

  async function onSubmit(values: PasswordResetRequestInput) {
    // Anti-enumeration: backend always returns 204. We surface a success
    // state regardless of whether the email exists.
    await fetch(
      variant === "platform"
        ? "/api/auth/platform-forgot-password"
        : "/api/auth/tenant-forgot-password",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
        credentials: "include",
      },
    ).catch(() => {});
    setSubmitted(true);
  }

  if (submitted) {
    return (
      <Card className="max-w-md p-8">
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">Check your email</h1>
        <p className="text-[var(--text-secondary)]">
          If an account exists for the address you entered, reset instructions
          will arrive shortly. Reset tokens expire after 15 minutes.
        </p>
        <p className="mt-4">
          <Link
            href={variant === "platform" ? "/platform/login" : "/login"}
            className="text-[var(--text-link)] hover:underline"
          >
            Back to sign in
          </Link>
        </p>
      </Card>
    );
  }

  return (
    <Card className="max-w-md p-8">
      <h1 className="mb-1 text-[var(--text-h3)] font-semibold">Reset password</h1>
      <p className="mb-6 text-[var(--text-secondary)]">
        We'll send instructions to the address you provide.
      </p>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <div>
          <Label htmlFor="email" required>
            Email
          </Label>
          <Input id="email" type="email" autoComplete="email" {...register("email")} />
          {errors.email && (
            <p className="mt-1 text-xs text-[var(--text-danger)]">
              {errors.email.message}
            </p>
          )}
        </div>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Sending…" : "Send reset instructions"}
        </Button>
      </form>
    </Card>
  );
}
```

You'll also need two thin Route Handlers that proxy `/platform/auth/password-reset/request` and `/auth/password-reset/request` — see the platform-login handler for the pattern. Add at `app/api/auth/platform-forgot-password/route.ts` and `app/api/auth/tenant-forgot-password/route.ts`.

- [ ] **Step 3: ResetPasswordForm + one-time-modal**

```tsx
// admin/apps/portal/src/components/forms/ResetPasswordForm.tsx
"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  passwordResetConfirmSchema,
  type PasswordResetConfirmInput,
} from "@sacco/schemas";
import { Button, Card, Input, Label } from "@sacco/ui";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { OneTimeModal } from "../OneTimeModal";

type Variant = "platform" | "tenant";

interface Props {
  variant: Variant;
}

export function ResetPasswordForm({ variant }: Props) {
  const router = useRouter();
  const params = useSearchParams();
  const initialToken = params.get("token") ?? "";
  const [serverError, setServerError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<PasswordResetConfirmInput>({
    resolver: zodResolver(passwordResetConfirmSchema),
    defaultValues: {
      token: initialToken,
      new_password: "",
      confirm_password: "",
    },
  });

  async function onSubmit(values: PasswordResetConfirmInput) {
    setServerError(null);
    const r = await fetch(
      variant === "platform"
        ? "/api/auth/platform-reset-password"
        : "/api/auth/tenant-reset-password",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: values.token,
          new_password: values.new_password,
        }),
        credentials: "include",
      },
    );
    if (!r.ok) {
      const detail = await r.json().catch(() => ({}));
      setServerError(detail?.detail ?? "Reset failed. The link may have expired.");
      return;
    }
    setSuccess(true);
  }

  if (success) {
    return (
      <Card className="max-w-md p-8">
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
          Password updated
        </h1>
        <p className="mb-4 text-[var(--text-secondary)]">
          Your new password is active. Sign in to continue.
        </p>
        <Link
          href={variant === "platform" ? "/platform/login" : "/login"}
          className="text-[var(--text-link)] hover:underline"
        >
          Back to sign in
        </Link>
      </Card>
    );
  }

  return (
    <Card className="max-w-md p-8">
      <h1 className="mb-1 text-[var(--text-h3)] font-semibold">Set a new password</h1>
      <p className="mb-6 text-[var(--text-secondary)]">
        Choose a password of at least 12 characters.
      </p>
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
        <div>
          <Label htmlFor="token" required>
            Reset token
          </Label>
          <Input id="token" type="text" {...register("token")} />
          {errors.token && (
            <p className="mt-1 text-xs text-[var(--text-danger)]">
              {errors.token.message}
            </p>
          )}
        </div>
        <div>
          <Label htmlFor="new_password" required>
            New password
          </Label>
          <Input
            id="new_password"
            type="password"
            autoComplete="new-password"
            {...register("new_password")}
          />
          {errors.new_password && (
            <p className="mt-1 text-xs text-[var(--text-danger)]">
              {errors.new_password.message}
            </p>
          )}
        </div>
        <div>
          <Label htmlFor="confirm_password" required>
            Confirm password
          </Label>
          <Input
            id="confirm_password"
            type="password"
            autoComplete="new-password"
            {...register("confirm_password")}
          />
          {errors.confirm_password && (
            <p className="mt-1 text-xs text-[var(--text-danger)]">
              {errors.confirm_password.message}
            </p>
          )}
        </div>
        {serverError && (
          <p
            role="alert"
            className="rounded-md bg-[var(--status-danger-bg)] p-3 text-sm text-[var(--text-danger)]"
          >
            {serverError}
          </p>
        )}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Updating…" : "Update password"}
        </Button>
      </form>
    </Card>
  );
}
```

Add corresponding Route Handlers for `/api/auth/platform-reset-password` and `/api/auth/tenant-reset-password` — proxy to `/platform/auth/password-reset/confirm` and `/auth/password-reset/confirm`.

- [ ] **Step 4: Pages — each just wraps the form**

```tsx
// admin/apps/portal/app/platform/forgot-password/page.tsx
import { ForgotPasswordForm } from "@/components/forms/ForgotPasswordForm";

export default function Page() {
  return (
    <main className="mx-auto grid min-h-screen max-w-3xl place-items-center p-8">
      <ForgotPasswordForm variant="platform" />
    </main>
  );
}
```

Repeat for `/platform/reset-password/page.tsx`, `/(tenant)/forgot-password/page.tsx`, `/(tenant)/reset-password/page.tsx`. Each is identical to the platform version except for the `variant` prop.

- [ ] **Step 5: Commit**

```bash
git add admin/apps/portal/src/components/ \
        admin/apps/portal/app/platform/ \
        admin/apps/portal/app/\(tenant\)/ \
        admin/apps/portal/app/api/auth/
git commit -m "feat(portal): OneTimeModal + forgot + reset forms + pages (platform + tenant)"
```

---

## Task 8: RTL + MSW tests for the auth forms

**Files:**
- Create: `admin/apps/portal/src/auth/__tests__/LoginForm.test.tsx`
- Create: `admin/apps/portal/src/auth/__tests__/middleware.test.ts`
- Create: `admin/apps/portal/vitest.config.ts`

- [ ] **Step 1: Vitest setup for the portal app**

```typescript
// admin/apps/portal/vitest.config.ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": resolve(__dirname, "./src") },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
  },
});
```

```typescript
// admin/apps/portal/vitest.setup.ts
import "@testing-library/jest-dom/vitest";
```

Add Vitest scripts + deps to `admin/apps/portal/package.json` if not already present (`vitest`, `@vitejs/plugin-react`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`, `msw`).

- [ ] **Step 2: LoginForm test**

```typescript
// admin/apps/portal/src/auth/__tests__/LoginForm.test.tsx
import { describe, expect, it, beforeAll, afterAll, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

// Mock useRouter / useSearchParams because next/navigation isn't available in
// jsdom out of the box.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { LoginForm } from "@/components/forms/LoginForm";

const server = setupServer(
  http.post("/api/auth/platform-login", async ({ request }) => {
    const body = (await request.json()) as { email: string; password: string };
    if (body.email === "good@test.example" && body.password === "GoodPass!2026") {
      return HttpResponse.json({ access_token: "abc", expires_in: 900 });
    }
    return new HttpResponse(JSON.stringify({ detail: "Invalid credentials" }), {
      status: 401,
    });
  }),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("LoginForm (platform)", () => {
  it("validates email format client-side", async () => {
    const user = userEvent.setup();
    render(<LoginForm variant="platform" />);
    await user.type(screen.getByLabelText(/email/i), "not-an-email");
    await user.type(screen.getByLabelText(/password/i), "x");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/valid email/i)).toBeInTheDocument();
  });

  it("surfaces 401 as user-visible error", async () => {
    const user = userEvent.setup();
    render(<LoginForm variant="platform" />);
    await user.type(screen.getByLabelText(/email/i), "wrong@test.example");
    await user.type(screen.getByLabelText(/password/i), "anything");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/invalid/i);
  });

  it("submits successfully", async () => {
    const user = userEvent.setup();
    render(<LoginForm variant="platform" />);
    await user.type(screen.getByLabelText(/email/i), "good@test.example");
    await user.type(screen.getByLabelText(/password/i), "GoodPass!2026");
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    // We don't assert the redirect; useRouter is mocked. The absence of a
    // visible error is the signal.
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
```

- [ ] **Step 3: Middleware tenant-resolver unit test**

```typescript
// admin/apps/portal/src/auth/__tests__/tenant-resolver.test.ts
import { describe, expect, it } from "vitest";
import { resolveTenantSlug } from "@/auth/tenant-resolver";

describe("resolveTenantSlug", () => {
  it("extracts subdomain in production", () => {
    expect(
      resolveTenantSlug({
        host: "sacco-one.app.sacco.example",
        searchParams: new URLSearchParams(),
        cookieValue: null,
        rootDomain: "app.sacco.example",
      }),
    ).toBe("sacco-one");
  });

  it("returns null for the root domain", () => {
    expect(
      resolveTenantSlug({
        host: "app.sacco.example",
        searchParams: new URLSearchParams(),
        cookieValue: null,
        rootDomain: "app.sacco.example",
      }),
    ).toBeNull();
  });

  it("falls back to query param in dev", () => {
    expect(
      resolveTenantSlug({
        host: "localhost:3000",
        searchParams: new URLSearchParams("tenant=sacco-two"),
        cookieValue: null,
      }),
    ).toBe("sacco-two");
  });

  it("falls back to cookie", () => {
    expect(
      resolveTenantSlug({
        host: "localhost:3000",
        searchParams: new URLSearchParams(),
        cookieValue: "sacco-three",
      }),
    ).toBe("sacco-three");
  });

  it("rejects malformed slugs", () => {
    expect(
      resolveTenantSlug({
        host: "localhost:3000",
        searchParams: new URLSearchParams("tenant=Bad..Slug"),
        cookieValue: null,
      }),
    ).toBeNull();
  });
});
```

- [ ] **Step 4: Run + commit**

```bash
cd admin
pnpm --filter @sacco/portal test
```
Expected: tests pass.

```bash
git add admin/apps/portal/vitest.config.ts \
        admin/apps/portal/vitest.setup.ts \
        admin/apps/portal/src/auth/__tests__/ \
        admin/apps/portal/package.json
git commit -m "test(portal): LoginForm + tenant-resolver unit tests"
```

---

## Task 9: Playwright E2E

**Files:**
- Create: `admin/apps/portal/playwright.config.ts`
- Create: `admin/apps/portal/tests/e2e/auth.spec.ts`

- [ ] **Step 1: Playwright config**

```typescript
// admin/apps/portal/playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    headless: true,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: "pnpm dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
```

- [ ] **Step 2: E2E spec**

```typescript
// admin/apps/portal/tests/e2e/auth.spec.ts
import { test, expect } from "@playwright/test";

test.describe("Auth shell", () => {
  test("redirects an unauthenticated GET of a protected page to /platform/login", async ({
    page,
  }) => {
    await page.goto("/platform");
    await expect(page).toHaveURL(/\/platform\/login\?next=%2Fplatform/);
  });

  test("login form renders with the right title", async ({ page }) => {
    await page.goto("/platform/login");
    await expect(
      page.getByRole("heading", { name: /platform sign in/i }),
    ).toBeVisible();
  });

  test("client-side validation rejects empty submission", async ({ page }) => {
    await page.goto("/platform/login");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByText(/valid email/i)).toBeVisible();
  });

  // Note: a full login → me → logout round trip requires a seeded
  // platform user. That belongs in CI sub-plan 39 against a Docker compose
  // stack with the real backend. Document here as a follow-up.
});
```

- [ ] **Step 3: Run**

```bash
cd admin
pnpm --filter @sacco/portal exec playwright install --with-deps
pnpm --filter @sacco/portal exec playwright test
```
Expected: 3 tests pass.

- [ ] **Step 4: Commit**

```bash
git add admin/apps/portal/playwright.config.ts \
        admin/apps/portal/tests/e2e/auth.spec.ts \
        admin/apps/portal/package.json
git commit -m "test(portal): Playwright E2E covering redirect + form rendering + validation"
```

---

## Task 10: Final verification

- [ ] **Step 1: Full pipeline**

```bash
cd admin
pnpm install
pnpm typecheck
pnpm lint
pnpm test
make admin-dev &
DEV_PID=$!
sleep 8
# Protected route redirects to login
curl -sI http://localhost:3000/platform | grep -i location
# Login pages render
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/platform/login
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/login
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/platform/forgot-password
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/platform/reset-password
kill $DEV_PID 2>/dev/null || true
```
Expected: typecheck/lint/test green; the protected-page response has a `Location: /platform/login` header; all login/forgot/reset pages return 200.

- [ ] **Step 2: Manual login round-trip (optional)**

```bash
make up
make migrate
make api &
make admin-dev &
sleep 8
# In a browser:
#   http://localhost:3000/platform/login
#   Email: admin@platform.example.com (from .env)
#   Password: AdminTest!2026
# Expect: redirect to /platform (which renders the sub-plan 04 placeholder
# home for now — sub-plan 08 lands the real app shell).
pkill -f "uvicorn app.main:app" || true
pkill -f "next dev" || true
```

- [ ] **Step 3: PR**

```bash
git push -u origin feat/portal-v1/07-auth-shell
gh pr create --title "feat(portal): auth shell (middleware + cookies + login/forgot/reset)" --body "$(cat <<'EOF'
## Summary
- httpOnly Secure SameSite=Strict refresh-token cookies (platform + tenant) owned by Next.js Route Handlers
- Access token in memory only (Zustand store; CookieBackedTokenStore implements `@sacco/api-client`'s `TokenStore` interface)
- Next.js middleware resolves tenant slug (subdomain in prod / query+cookie in dev), redirects unauthenticated GETs of protected routes to the right login
- Shared LoginForm + ForgotPasswordForm + ResetPasswordForm components keyed by `variant: "platform" | "tenant"`
- Six pages: platform & tenant × login / forgot / reset
- Six Route Handlers: platform & tenant × login / refresh / logout (forgot + reset proxies in the same directory)
- Reusable OneTimeModal (used by reset success today; powers admin-initiated reset in sub-plan 32)
- Sub-plan 05 amendment: `refreshMiddleware` skips JSON body and uses `credentials:include` when the token store returns `null` for the refresh token (the cookie-backed path)
- Lockout response surfaced as a user-visible "Account locked" alert
- RTL + MSW coverage for the LoginForm and tenant-resolver
- Playwright E2E covering redirect → login render → client-side validation

## Out of scope
- App shell (sub-plan 08) — auth-protected route groups with header/sidebar still pending
- Display primitives — `<Money>`, `<FormattedDate>` etc. land in sub-plan 09
- DataTable, form primitives — sub-plans 10, 11

## Test plan
- [ ] `pnpm --filter @sacco/api-client test` (cookie-backed refresh)
- [ ] `pnpm --filter @sacco/portal test` (LoginForm + resolver)
- [ ] `pnpm --filter @sacco/portal exec playwright test`
- [ ] `make ci` clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] Sub-plan 05's `refreshMiddleware` skips JSON body when `getRefreshToken()` is null (cookie path) + test
- [ ] Cookie helpers + `CookieBackedTokenStore` + tenant-resolver + server-helper modules in place
- [ ] Six Route Handlers (login/refresh/logout × platform/tenant) + four forgot/reset proxy handlers
- [ ] `middleware.ts` resolves tenant context, redirects unauthenticated GETs
- [ ] `AuthProvider` wraps the app with `QueryClientProvider` + memoised api-client
- [ ] Six pages render and pass smoke checks (platform/tenant × login/forgot/reset)
- [ ] `OneTimeModal` blocks dismissal until acknowledged + provides copy-to-clipboard
- [ ] Lockout 423/locked-detail surfaces as a friendly message
- [ ] RTL + MSW tests pass; Playwright E2E passes
- [ ] PR opened, CI green

## Notes for the executing subagent

- **Do not** persist the access token to localStorage or sessionStorage. It lives in memory only. After a page reload, the AuthProvider's `useEffect` either re-mints it from the refresh route or, if no cookie is present, leaves the user unauthenticated and the middleware redirects.
- **Do not** read the refresh token from JS. Even in dev, the cookie is httpOnly. If a test needs to assert the cookie is set, use `document.cookie` (which won't show httpOnly entries) or inspect the response headers in the Route Handler test.
- **Do not** weaken the cookie attributes. `SameSite=Strict` is the contract from CLAUDE.md C. Production cookies are `Secure: true`; dev allows `false` because dev runs over HTTP.
- **Do not** add an "OAuth" or "SSO" provider here. The portal speaks only to FastAPI's password endpoints in v1. Future SSO providers will piggy-back on the same Route Handler boundary.
- **Do not** call FastAPI from client components for auth. The Route Handlers are the only path. The api-client middleware (sub-plan 05) uses `/api/auth/*` URLs, not `/platform/auth/*` directly.
- The middleware path matcher uses Next.js's matcher syntax. If you add new public paths (e.g., for an embedded marketing page), update `PUBLIC_PATHS_PLATFORM` / `PUBLIC_PATHS_TENANT` accordingly.
- `getServerAccessToken()` returns null today. Sub-plan 08 ships the actual server-side token plumbing (per-request token from a server cache or by calling refresh during RSC render). Keep it as a stub here so server components compile.
- The `/api/auth/platform-forgot-password` and `/api/auth/tenant-forgot-password` Route Handlers are stubbed in the task description but you'll need to write them. They mirror the login handler's structure but call `/platform/auth/password-reset/request` / `/auth/password-reset/request` and always return 204 (the backend already does this).
- The OneTimeModal explicitly disables overlay and Escape-key dismissal so the user must click the acknowledge button. This is intentional per CLAUDE.md contract F. Do not "fix" this for UX.
- If `pnpm exec playwright install` fails behind a corporate proxy, the executor environment may need `PLAYWRIGHT_DOWNLOAD_HOST` or `HTTP_PROXY` configured. Document any workaround in the PR.
- The auth shell does not handle Phase 1.7's role-based gating. That comes in sub-plan 08 (`<PermissionGuard>` and the `requirePermission()` helper). Until then, the only auth state is "logged in" or "not".
- This sub-plan does not consume the `useAuth()` hook from a real screen — the home page placeholder from sub-plan 04 still renders. Sub-plan 08's app shell is the first real consumer.
- If `make admin-dev` fails to start because `apps/portal` is missing a dependency, run `make admin-install` first. The package.json in this sub-plan adds several new runtime deps.
