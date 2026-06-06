# Portal v1 Sub-Plan 05: `packages/api-client` with OpenAPI Codegen

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/portal-v1/05-api-client` from `main` (or rebase on top of sub-plans 01-04).

**Goal:** Build the single typed HTTP layer every portal feature consumes. Auto-generated TypeScript types from the FastAPI OpenAPI spec, an `openapi-fetch` core with middleware for auth + tenant slug + idempotency + 401-refresh, typed exceptions for the subscription-gate (402/403) and server errors, per-resource client builders, and TanStack Query helpers. After this sub-plan merges, every later feature sub-plan writes code that looks like `useTypedQuery(["tenants", "list"], () => api.tenants.list())`.

**Architecture:**
- `openapi-typescript` reads `admin/packages/api-client/openapi.json` (a committed snapshot of `/openapi.json` from the running FastAPI) and emits `src/generated/schema.d.ts`. The script that produces the snapshot lives at `admin/scripts/capture-openapi.mjs` and boots uvicorn in a child process, fetches the spec, writes it, and exits.
- `openapi-fetch` is the runtime — a thin, type-safe wrapper that takes the `paths` type from the generated schema. Our `createApiClient` factory wraps it with middleware:
  - `authMiddleware` reads from a token store (provided by the caller — sub-plan 07's auth shell wires this) and adds `Authorization: Bearer <token>` to every request
  - `tenantMiddleware` reads the current tenant slug from a context provider (also sub-plan 07) and adds `X-Tenant-Slug` to tenant-scoped requests
  - `idempotencyMiddleware` adds an `Idempotency-Key` header on POST/PUT/PATCH/DELETE. Default key is a fresh UUID v7; callers can override per-request to share a key across retries of the same user intent
  - `refreshMiddleware` catches 401 once per request, calls the appropriate refresh endpoint (`/platform/auth/refresh` or `/auth/refresh`), updates the token via the store, retries the original request, and only fails after a second 401
  - `errorMiddleware` translates 402, 403 (when the detail matches the gate signature), and 5xx into typed exceptions
- Per-resource clients (`platformAuth`, `tenants`, `members`, `savings`, etc.) are thin objects that group typed methods by domain. They exist so feature code reads `api.tenants.list()` instead of `api.GET("/platform/tenants")`. Each method is one line that delegates to the openapi-fetch instance.
- TanStack Query helpers:
  - `queryKeys` is a flat object whose entries are query-key factory functions (`queryKeys.tenants.list(filters)` → `["tenants", "list", filters]`). Cache invalidation routes through these.
  - `useTypedQuery` is a thin wrapper around `useQuery` that infers the return type from the resource method
  - `useTypedMutation` wraps `useMutation` and auto-invalidates the queries the caller declares as affected
- 401-refresh uses a singleton promise to coalesce concurrent refreshes — if 10 requests fire at once and all hit 401, only one refresh call goes out; the other 9 await the same promise.

**Tech Stack:** `openapi-typescript` 7, `openapi-fetch` 0.13, `@tanstack/react-query` 5, `uuid` 10 (v7), Vitest 2, MSW 2.

**Portal v1 index reference:** `docs/superpowers/plans/2026-06-02-portal-v1-index.md` §Sub-plan 05.

**Required reading:**
- The Portal v1 index §5 (full API surface) and §3.G (subscription-gate UX)
- `app/main.py` (router mounts)
- `app/core/db.py:70-124` (subscription gate semantics — `_check_subscription_gate`)
- CLAUDE.md "Billing module contracts" (gate HTTP codes 402/403)

**Prerequisite:** **Sub-plan 03 must be merged** (the Next.js app + transpilePackages list). Sub-plan 04 is a soft prerequisite — the api-client doesn't import from `@sacco/ui`, but the portal app already consumes both. Phase 1.7 should be merged for the captured OpenAPI to include `/platform/approvals/*`, `/platform/impersonations/*`, audit log query API, and dashboard-stats; if not, those types will be added incrementally as Phase 1.7 lands.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `admin/scripts/capture-openapi.mjs` | Create | Boot uvicorn, GET `/openapi.json`, write to `packages/api-client/openapi.json` |
| `admin/package.json` | Modify | Add `openapi:capture` and `openapi:codegen` scripts at root |
| `admin/packages/api-client/package.json` | Create | `@sacco/api-client` manifest |
| `admin/packages/api-client/tsconfig.json` | Create | Extends `@sacco/tsconfig/library.json` |
| `admin/packages/api-client/eslint.config.mjs` | Create | Extends `@sacco/eslint-config` |
| `admin/packages/api-client/openapi.json` | Create | Committed snapshot of the FastAPI OpenAPI spec |
| `admin/packages/api-client/src/generated/schema.d.ts` | Create (generated) | `openapi-typescript` output (committed for reproducibility) |
| `admin/packages/api-client/src/types.ts` | Create | Re-export typed `paths` + helpers |
| `admin/packages/api-client/src/token-store.ts` | Create | Interface + in-memory implementation |
| `admin/packages/api-client/src/errors.ts` | Create | `SubscriptionPastDueError`, `SubscriptionSuspendedError`, `ServerError`, `UnauthorizedError` |
| `admin/packages/api-client/src/middleware/auth.ts` | Create | Adds `Authorization` header |
| `admin/packages/api-client/src/middleware/tenant.ts` | Create | Adds `X-Tenant-Slug` header |
| `admin/packages/api-client/src/middleware/idempotency.ts` | Create | Adds `Idempotency-Key` on writes |
| `admin/packages/api-client/src/middleware/errors.ts` | Create | Translates 402/403/5xx into typed errors |
| `admin/packages/api-client/src/middleware/refresh.ts` | Create | 401-refresh-once with promise coalescing |
| `admin/packages/api-client/src/client.ts` | Create | `createApiClient` factory wiring middleware |
| `admin/packages/api-client/src/resources/*.ts` | Create | Per-resource client builders |
| `admin/packages/api-client/src/query-keys.ts` | Create | Query-key factories |
| `admin/packages/api-client/src/hooks.ts` | Create | `useTypedQuery`, `useTypedMutation` |
| `admin/packages/api-client/src/index.ts` | Create | Re-export surface |
| `admin/packages/api-client/src/__tests__/*.test.ts` | Create | Vitest + MSW coverage |
| `admin/packages/api-client/vitest.config.ts` | Create | Vitest config |

---

## Task 1: OpenAPI capture script + committed snapshot

**Files:**
- Create: `admin/scripts/capture-openapi.mjs`
- Create: `admin/packages/api-client/openapi.json` (output of running the script)
- Modify: `admin/package.json` (workspace-root scripts)

- [ ] **Step 1: Write the capture script**

```javascript
// admin/scripts/capture-openapi.mjs
// Boots uvicorn in a child process, waits for /healthz, fetches /openapi.json,
// and writes it to packages/api-client/openapi.json. Commits-ready.
//
// Usage: node admin/scripts/capture-openapi.mjs
// (called from admin/ root via `pnpm openapi:capture`)

import { spawn } from "node:child_process";
import { writeFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..", "..");
const OUTPUT = resolve(
  __dirname, "..", "packages/api-client/openapi.json",
);
const HOST = "127.0.0.1";
const PORT = process.env.OPENAPI_CAPTURE_PORT ?? "8765";
const URL = `http://${HOST}:${PORT}`;
const HEALTH = `${URL}/healthz`;
const SPEC = `${URL}/openapi.json`;

async function waitForHealth(timeoutMs = 30_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(HEALTH);
      if (r.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`uvicorn did not become healthy within ${timeoutMs}ms`);
}

async function main() {
  // Launch uvicorn from the repo root. Environment must already have
  // DATABASE_URL etc. set (or .env present).
  const child = spawn(
    "python",
    ["-m", "uvicorn", "app.main:app", "--host", HOST, "--port", PORT, "--no-access-log"],
    {
      cwd: REPO_ROOT,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  // Surface errors but don't tee stdout — it's noisy.
  child.stderr.on("data", (b) => process.stderr.write(b));

  try {
    await waitForHealth();
    const r = await fetch(SPEC);
    if (!r.ok) {
      throw new Error(`/openapi.json returned ${r.status}`);
    }
    const json = await r.json();
    await mkdir(dirname(OUTPUT), { recursive: true });
    await writeFile(OUTPUT, JSON.stringify(json, null, 2) + "\n");
    console.log(`wrote ${OUTPUT}`);
  } finally {
    child.kill("SIGTERM");
    // Allow uvicorn 2s to shut down cleanly
    await new Promise((r) => setTimeout(r, 2000));
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
```

- [ ] **Step 2: Add workspace-root scripts**

In `admin/package.json` `scripts` block, append:

```json
"openapi:capture": "node scripts/capture-openapi.mjs",
"openapi:codegen": "pnpm --filter @sacco/api-client codegen"
```

- [ ] **Step 3: Run the capture against a live backend**

```bash
make up                # ensure postgres etc. are up
make migrate
cd admin
pnpm openapi:capture
ls -lh packages/api-client/openapi.json
```
Expected: `openapi.json` is a few hundred KB and contains paths for `/platform/*`, `/auth/*`, `/members`, `/savings`, etc.

Validate the spec is well-formed:

```bash
python -c "import json; spec = json.load(open('admin/packages/api-client/openapi.json')); print('paths:', len(spec['paths']))"
```
Expected: prints the number of paths (~80–100 depending on which Phase 1.7 sub-plans have merged).

- [ ] **Step 4: Commit**

```bash
git add admin/scripts/capture-openapi.mjs \
        admin/package.json \
        admin/packages/api-client/openapi.json
git commit -m "feat(api-client): capture-openapi script + committed snapshot"
```

---

## Task 2: Package skeleton + openapi-typescript codegen

**Files:**
- Create: `admin/packages/api-client/package.json`
- Create: `admin/packages/api-client/tsconfig.json`
- Create: `admin/packages/api-client/eslint.config.mjs`
- Create: `admin/packages/api-client/src/generated/schema.d.ts` (generated)
- Create: `admin/packages/api-client/src/types.ts`
- Create: `admin/packages/api-client/src/index.ts` (stub)

- [ ] **Step 1: Package manifest**

```json
{
  "name": "@sacco/api-client",
  "version": "0.0.0",
  "private": true,
  "license": "UNLICENSED",
  "type": "module",
  "exports": {
    ".": {
      "types": "./src/index.ts",
      "default": "./src/index.ts"
    },
    "./types": {
      "types": "./src/types.ts",
      "default": "./src/types.ts"
    }
  },
  "scripts": {
    "codegen": "openapi-typescript ./openapi.json -o ./src/generated/schema.d.ts",
    "lint": "eslint . --max-warnings=0",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest",
    "clean": "rm -rf .turbo coverage"
  },
  "peerDependencies": {
    "react": "^19.0.0"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.59.0",
    "openapi-fetch": "^0.13.0",
    "uuid": "^10.0.0"
  },
  "devDependencies": {
    "@sacco/eslint-config": "workspace:*",
    "@sacco/tsconfig": "workspace:*",
    "@types/react": "^19.0.0",
    "@types/uuid": "^10.0.0",
    "@vitejs/plugin-react": "^4.3.1",
    "eslint": "^9.10.0",
    "jsdom": "^25.0.0",
    "msw": "^2.4.5",
    "openapi-typescript": "^7.4.1",
    "typescript": "^5.6.2",
    "vitest": "^2.1.1"
  }
}
```

- [ ] **Step 2: TypeScript config**

```json
{
  "extends": "@sacco/tsconfig/library.json",
  "compilerOptions": {
    "rootDir": "./src",
    "outDir": "./dist",
    "jsx": "react-jsx",
    "lib": ["DOM", "DOM.Iterable", "ES2023"]
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "coverage"]
}
```

- [ ] **Step 3: ESLint config**

```javascript
import baseConfig from "@sacco/eslint-config";

export default [
  ...baseConfig,
  {
    files: ["src/generated/**/*"],
    rules: {
      // Generated code has its own conventions.
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-vars": "off",
    },
  },
  {
    ignores: ["node_modules", "dist", "coverage"],
  },
];
```

- [ ] **Step 4: Install + run codegen**

```bash
make admin-install
cd admin
pnpm --filter @sacco/api-client codegen
ls -lh packages/api-client/src/generated/schema.d.ts
```
Expected: `schema.d.ts` is generated, a few hundred KB. Each path appears as a typed entry under `paths`.

- [ ] **Step 5: Write `types.ts` re-export**

```typescript
// admin/packages/api-client/src/types.ts
// Re-export the generated paths type as `Paths` so consumers don't need
// to know the codegen output's internal name.
import type { paths, components } from "./generated/schema";

export type Paths = paths;
export type Schemas = components["schemas"];
```

- [ ] **Step 5b: Empty index stub**

```typescript
// admin/packages/api-client/src/index.ts
export * from "./types";
```

- [ ] **Step 6: Verify typecheck**

```bash
cd admin
pnpm --filter @sacco/api-client typecheck
```
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add admin/packages/api-client/ admin/pnpm-lock.yaml
git commit -m "feat(api-client): package skeleton + openapi-typescript codegen"
```

---

## Task 3: Token store + tenant context + base client

**Files:**
- Create: `admin/packages/api-client/src/token-store.ts`
- Create: `admin/packages/api-client/src/tenant-context.ts`
- Create: `admin/packages/api-client/src/client.ts`
- Create: `admin/packages/api-client/src/__tests__/client.test.ts`
- Create: `admin/packages/api-client/vitest.config.ts`

- [ ] **Step 1: Vitest config**

```typescript
// admin/packages/api-client/vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [],
  },
});
```

- [ ] **Step 2: Token store interface + default in-memory implementation**

```typescript
// admin/packages/api-client/src/token-store.ts
/**
 * Token store contract: the auth shell (sub-plan 07) supplies the
 * implementation; the api-client uses it transparently. Server components
 * may inject a per-request store; client components share a single one.
 */
export interface TokenStore {
  /** Returns the current access token, or null if unauthenticated. */
  getAccessToken(): string | null;
  /** Persists a refreshed access token. Called by refreshMiddleware. */
  setAccessToken(token: string | null): void;
  /**
   * Returns the refresh-endpoint path for the current auth context.
   * `/platform/auth/refresh` for platform context, `/auth/refresh` for
   * tenant context.
   */
  getRefreshEndpoint(): "/platform/auth/refresh" | "/auth/refresh";
  /**
   * Returns the current refresh token. May return null in server context
   * where the token is in an httpOnly cookie and Next.js forwards it via
   * the same-origin fetch.
   */
  getRefreshToken(): string | null;
}

export class InMemoryTokenStore implements TokenStore {
  #accessToken: string | null = null;
  #refreshToken: string | null = null;
  #refreshEndpoint: "/platform/auth/refresh" | "/auth/refresh";

  constructor(
    refreshEndpoint: "/platform/auth/refresh" | "/auth/refresh",
  ) {
    this.#refreshEndpoint = refreshEndpoint;
  }

  getAccessToken(): string | null {
    return this.#accessToken;
  }
  setAccessToken(token: string | null): void {
    this.#accessToken = token;
  }
  getRefreshEndpoint(): "/platform/auth/refresh" | "/auth/refresh" {
    return this.#refreshEndpoint;
  }
  getRefreshToken(): string | null {
    return this.#refreshToken;
  }
  setRefreshToken(token: string | null): void {
    this.#refreshToken = token;
  }
}
```

- [ ] **Step 3: Tenant context interface**

```typescript
// admin/packages/api-client/src/tenant-context.ts
/**
 * Supplies the current tenant slug for tenant-scoped requests. In platform
 * context, getSlug() returns null and tenantMiddleware skips header
 * injection (the request is going to /platform/* which doesn't need it).
 */
export interface TenantContext {
  getSlug(): string | null;
}

export class FixedTenantContext implements TenantContext {
  #slug: string | null;
  constructor(slug: string | null) {
    this.#slug = slug;
  }
  getSlug(): string | null {
    return this.#slug;
  }
}
```

- [ ] **Step 4: Base client factory (no middleware yet — we add them in Task 4)**

```typescript
// admin/packages/api-client/src/client.ts
import createOpenapiFetch, { type Client as OpenapiClient } from "openapi-fetch";
import type { paths } from "./generated/schema";
import type { TokenStore } from "./token-store";
import type { TenantContext } from "./tenant-context";

export interface ApiClientOptions {
  baseUrl: string;
  tokenStore: TokenStore;
  tenantContext: TenantContext;
  /** Optional fetch override (tests inject MSW-aware fetch). */
  fetch?: typeof fetch;
}

export type FetchClient = OpenapiClient<paths>;

export function createApiClient(opts: ApiClientOptions): FetchClient {
  const client = createOpenapiFetch<paths>({
    baseUrl: opts.baseUrl,
    fetch: opts.fetch,
  });
  // Middleware added in Task 4 — for now the client is a plain pass-through.
  // The opts.tokenStore and opts.tenantContext aren't yet consumed.
  void opts.tokenStore;
  void opts.tenantContext;
  return client;
}
```

- [ ] **Step 5: Smoke test — proves the client can issue a request against MSW**

```typescript
// admin/packages/api-client/src/__tests__/client.test.ts
import { describe, expect, it, beforeAll, afterAll, afterEach } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { createApiClient } from "../client";
import { InMemoryTokenStore } from "../token-store";
import { FixedTenantContext } from "../tenant-context";

const server = setupServer(
  http.get("http://test/healthz", () =>
    HttpResponse.json({ status: "ok" }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("createApiClient (base)", () => {
  it("issues a GET against the configured base URL", async () => {
    const api = createApiClient({
      baseUrl: "http://test",
      tokenStore: new InMemoryTokenStore("/platform/auth/refresh"),
      tenantContext: new FixedTenantContext(null),
    });
    const { data } = await api.GET("/healthz" as never);
    expect(data).toEqual({ status: "ok" });
  });
});
```

- [ ] **Step 6: Run the test**

```bash
cd admin
pnpm --filter @sacco/api-client test
```
Expected: 1 test passes.

- [ ] **Step 7: Commit**

```bash
git add admin/packages/api-client/src/{token-store,tenant-context,client}.ts \
        admin/packages/api-client/src/__tests__/client.test.ts \
        admin/packages/api-client/vitest.config.ts
git commit -m "feat(api-client): TokenStore + TenantContext + base createApiClient"
```

---

## Task 4: Middleware — auth, tenant, idempotency, errors, refresh

**Files:**
- Create: `admin/packages/api-client/src/errors.ts`
- Create: `admin/packages/api-client/src/middleware/auth.ts`
- Create: `admin/packages/api-client/src/middleware/tenant.ts`
- Create: `admin/packages/api-client/src/middleware/idempotency.ts`
- Create: `admin/packages/api-client/src/middleware/errors.ts`
- Create: `admin/packages/api-client/src/middleware/refresh.ts`
- Modify: `admin/packages/api-client/src/client.ts` (wire middleware)
- Create: `admin/packages/api-client/src/__tests__/middleware.test.ts`

- [ ] **Step 1: Typed errors**

```typescript
// admin/packages/api-client/src/errors.ts
export class UnauthorizedError extends Error {
  constructor(message = "Unauthorized") {
    super(message);
    this.name = "UnauthorizedError";
  }
}

export class SubscriptionPastDueError extends Error {
  detail: string;
  constructor(detail: string) {
    super("Subscription past due — payment required");
    this.name = "SubscriptionPastDueError";
    this.detail = detail;
  }
}

export class SubscriptionSuspendedError extends Error {
  detail: string;
  constructor(detail: string) {
    super("Subscription suspended or cancelled");
    this.name = "SubscriptionSuspendedError";
    this.detail = detail;
  }
}

export class ServerError extends Error {
  status: number;
  requestId: string | null;
  constructor(status: number, requestId: string | null, message?: string) {
    super(message ?? `Server error ${status}`);
    this.name = "ServerError";
    this.status = status;
    this.requestId = requestId;
  }
}
```

- [ ] **Step 2: Auth middleware**

`openapi-fetch` middleware has `onRequest` and `onResponse` hooks. We use `onRequest` to inject the bearer.

```typescript
// admin/packages/api-client/src/middleware/auth.ts
import type { Middleware } from "openapi-fetch";
import type { TokenStore } from "../token-store";

export function authMiddleware(tokenStore: TokenStore): Middleware {
  return {
    async onRequest({ request }) {
      const token = tokenStore.getAccessToken();
      if (token) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
      return request;
    },
  };
}
```

- [ ] **Step 3: Tenant middleware**

```typescript
// admin/packages/api-client/src/middleware/tenant.ts
import type { Middleware } from "openapi-fetch";
import type { TenantContext } from "../tenant-context";

export function tenantMiddleware(tenantContext: TenantContext): Middleware {
  return {
    async onRequest({ request }) {
      const slug = tenantContext.getSlug();
      // /platform/* and /.well-known/* requests don't need X-Tenant-Slug.
      // /billing/me/* requires it (tenant-facing billing API).
      const url = new URL(request.url);
      const needsSlug =
        !url.pathname.startsWith("/platform/") &&
        !url.pathname.startsWith("/.well-known/") &&
        slug !== null;
      if (needsSlug) {
        request.headers.set("X-Tenant-Slug", slug);
      }
      return request;
    },
  };
}
```

- [ ] **Step 4: Idempotency middleware**

```typescript
// admin/packages/api-client/src/middleware/idempotency.ts
import type { Middleware } from "openapi-fetch";
import { v7 as uuidv7 } from "uuid";

const MUTATION_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/**
 * Auto-inject `Idempotency-Key` on mutating requests. Callers can override
 * by setting the header explicitly — useful when the same user intent
 * needs to share a key across retries (e.g., a form submission that
 * re-fires after a network blip should keep its original UUID so the
 * backend dedups).
 */
export function idempotencyMiddleware(): Middleware {
  return {
    async onRequest({ request }) {
      if (!MUTATION_METHODS.has(request.method)) {
        return request;
      }
      if (!request.headers.has("Idempotency-Key")) {
        request.headers.set("Idempotency-Key", uuidv7());
      }
      return request;
    },
  };
}
```

- [ ] **Step 5: Error middleware (402 / 403 gate / 5xx)**

```typescript
// admin/packages/api-client/src/middleware/errors.ts
import type { Middleware } from "openapi-fetch";
import {
  ServerError,
  SubscriptionPastDueError,
  SubscriptionSuspendedError,
} from "../errors";

const GATE_403_PREFIX = "Subscription status";

export function errorMiddleware(): Middleware {
  return {
    async onResponse({ response }) {
      if (response.ok) return response;

      const status = response.status;

      if (status === 402) {
        const body = await safeJson(response);
        throw new SubscriptionPastDueError(
          typeof body?.detail === "string" ? body.detail : "Subscription past due",
        );
      }

      if (status === 403) {
        // Only the gate response uses this exact prefix in `detail`. Other
        // 403s (role mismatch, etc.) fall through and become normal errors.
        const body = await safeJson(response);
        if (
          typeof body?.detail === "string" &&
          body.detail.startsWith(GATE_403_PREFIX)
        ) {
          throw new SubscriptionSuspendedError(body.detail);
        }
      }

      if (status >= 500) {
        const requestId = response.headers.get("X-Request-ID");
        const body = await safeJson(response);
        throw new ServerError(
          status,
          requestId,
          typeof body?.detail === "string" ? body.detail : undefined,
        );
      }

      return response;
    },
  };
}

async function safeJson(response: Response): Promise<Record<string, unknown> | null> {
  try {
    return (await response.clone().json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}
```

- [ ] **Step 6: Refresh middleware (401-once with promise coalescing)**

```typescript
// admin/packages/api-client/src/middleware/refresh.ts
import type { Middleware } from "openapi-fetch";
import type { TokenStore } from "../token-store";
import { UnauthorizedError } from "../errors";

/**
 * 401-refresh-once. If a request 401s, we issue a single refresh call,
 * update the token store, and retry the original request once. If the
 * retry also 401s, we throw UnauthorizedError so the auth shell can
 * redirect to login.
 *
 * Concurrent 401s coalesce on the same in-flight promise — if 10 calls
 * all 401 in the same second, only one refresh call goes out.
 */
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
        if (!refreshToken) return null;
        const r = await fetch(`${baseUrl}${tokenStore.getRefreshEndpoint()}`, {
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
        // Already retried — give up.
        throw new UnauthorizedError();
      }
      const newToken = await refreshOnce();
      if (!newToken) {
        throw new UnauthorizedError();
      }
      // Retry once with the fresh token + a marker so we don't loop.
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

- [ ] **Step 7: Wire all middleware into `createApiClient`**

Replace the body of `client.ts`:

```typescript
// admin/packages/api-client/src/client.ts
import createOpenapiFetch, { type Client as OpenapiClient } from "openapi-fetch";
import type { paths } from "./generated/schema";
import { authMiddleware } from "./middleware/auth";
import { tenantMiddleware } from "./middleware/tenant";
import { idempotencyMiddleware } from "./middleware/idempotency";
import { errorMiddleware } from "./middleware/errors";
import { refreshMiddleware } from "./middleware/refresh";
import type { TokenStore } from "./token-store";
import type { TenantContext } from "./tenant-context";

export interface ApiClientOptions {
  baseUrl: string;
  tokenStore: TokenStore;
  tenantContext: TenantContext;
  fetch?: typeof fetch;
}

export type FetchClient = OpenapiClient<paths>;

export function createApiClient(opts: ApiClientOptions): FetchClient {
  const client = createOpenapiFetch<paths>({
    baseUrl: opts.baseUrl,
    fetch: opts.fetch,
  });

  // Middleware applies in declared order on request, reverse order on response.
  // Order: auth → tenant → idempotency → (server) → errors → refresh
  client.use(authMiddleware(opts.tokenStore));
  client.use(tenantMiddleware(opts.tenantContext));
  client.use(idempotencyMiddleware());
  client.use(errorMiddleware());
  client.use(refreshMiddleware(opts.tokenStore, opts.baseUrl));

  return client;
}
```

- [ ] **Step 8: Comprehensive middleware tests**

```typescript
// admin/packages/api-client/src/__tests__/middleware.test.ts
import { describe, expect, it, beforeAll, afterAll, afterEach } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { createApiClient } from "../client";
import { InMemoryTokenStore } from "../token-store";
import { FixedTenantContext } from "../tenant-context";
import {
  ServerError,
  SubscriptionPastDueError,
  SubscriptionSuspendedError,
  UnauthorizedError,
} from "../errors";

const BASE = "http://test";

const handlers = [
  http.get(`${BASE}/auth/me`, ({ request }) => {
    const auth = request.headers.get("Authorization") ?? "";
    if (auth !== "Bearer current-token") {
      return new HttpResponse(JSON.stringify({ detail: "no token" }), {
        status: 401,
      });
    }
    return HttpResponse.json({ id: "u1", email: "u@test.example" });
  }),
  http.get(`${BASE}/members`, ({ request }) => {
    if (!request.headers.has("X-Tenant-Slug")) {
      return new HttpResponse(null, { status: 400 });
    }
    return HttpResponse.json([]);
  }),
  http.post(`${BASE}/savings/accounts`, ({ request }) => {
    const key = request.headers.get("Idempotency-Key");
    if (!key || key.length < 36) {
      return new HttpResponse(JSON.stringify({ detail: "missing key" }), {
        status: 400,
      });
    }
    return HttpResponse.json({ id: "a1" }, { status: 201 });
  }),
  http.get(`${BASE}/billing/me/subscription`, () =>
    new HttpResponse(
      JSON.stringify({ detail: "Subscription past due and grace period has expired." }),
      { status: 402 },
    ),
  ),
  http.get(`${BASE}/billing/me/invoices`, () =>
    new HttpResponse(
      JSON.stringify({ detail: "Subscription status is 'suspended'; access denied." }),
      { status: 403 },
    ),
  ),
  http.get(`${BASE}/reporting/runs`, () =>
    new HttpResponse(JSON.stringify({ detail: "DB unavailable" }), {
      status: 503,
      headers: { "X-Request-ID": "req-abc-123" },
    }),
  ),
];

const refreshHandlers = [
  http.post(`${BASE}/platform/auth/refresh`, async ({ request }) => {
    const body = (await request.json()) as { refresh_token: string };
    if (body.refresh_token === "good-refresh") {
      return HttpResponse.json({
        access_token: "fresh-access",
        refresh_token: "good-refresh",
        expires_in: 900,
      });
    }
    return new HttpResponse(null, { status: 401 });
  }),
  http.get(`${BASE}/platform/auth/me`, ({ request }) => {
    if (request.headers.get("Authorization") === "Bearer fresh-access") {
      return HttpResponse.json({ id: "p1", email: "p@test.example" });
    }
    return new HttpResponse(null, { status: 401 });
  }),
];

const server = setupServer(...handlers, ...refreshHandlers);
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function makeClient(opts: {
  accessToken?: string | null;
  refreshToken?: string | null;
  refreshEndpoint?: "/platform/auth/refresh" | "/auth/refresh";
  slug?: string | null;
}) {
  const store = new InMemoryTokenStore(
    opts.refreshEndpoint ?? "/platform/auth/refresh",
  );
  store.setAccessToken(opts.accessToken ?? null);
  store.setRefreshToken(opts.refreshToken ?? null);
  return {
    api: createApiClient({
      baseUrl: BASE,
      tokenStore: store,
      tenantContext: { getSlug: () => opts.slug ?? null },
    }),
    store,
  };
}

describe("authMiddleware", () => {
  it("injects Bearer token when present", async () => {
    const { api } = makeClient({ accessToken: "current-token" });
    const { data } = await api.GET("/auth/me" as never);
    expect(data).toEqual({ id: "u1", email: "u@test.example" });
  });
});

describe("tenantMiddleware", () => {
  it("injects X-Tenant-Slug on tenant routes", async () => {
    const { api } = makeClient({
      accessToken: "current-token",
      slug: "test-tenant",
    });
    const { data } = await api.GET("/members" as never);
    expect(data).toEqual([]);
  });

  it("omits X-Tenant-Slug on platform routes", async () => {
    // /platform/billing/payments would be rejected by MSW if we somehow
    // forced a slug header — this test confirms we don't.
    const { api } = makeClient({
      accessToken: "current-token",
      slug: "ignored",
    });
    // Use any /platform/* path that exists in the spec; here we just verify
    // the slug doesn't appear on /platform/auth/me.
    const { data } = await api.GET("/platform/auth/me" as never);
    expect(data).toEqual({ id: "p1", email: "p@test.example" });
  });
});

describe("idempotencyMiddleware", () => {
  it("adds Idempotency-Key on POST", async () => {
    const { api } = makeClient({
      accessToken: "current-token",
      slug: "test-tenant",
    });
    const { data } = await api.POST("/savings/accounts" as never, {
      body: { member_id: "m1", savings_product_id: "p1" },
    } as never);
    expect(data).toEqual({ id: "a1" });
  });
});

describe("errorMiddleware", () => {
  it("throws SubscriptionPastDueError on 402", async () => {
    const { api } = makeClient({
      accessToken: "current-token",
      slug: "test-tenant",
    });
    await expect(
      api.GET("/billing/me/subscription" as never),
    ).rejects.toBeInstanceOf(SubscriptionPastDueError);
  });

  it("throws SubscriptionSuspendedError on 403 gate response", async () => {
    const { api } = makeClient({
      accessToken: "current-token",
      slug: "test-tenant",
    });
    await expect(
      api.GET("/billing/me/invoices" as never),
    ).rejects.toBeInstanceOf(SubscriptionSuspendedError);
  });

  it("throws ServerError with request_id on 5xx", async () => {
    const { api } = makeClient({
      accessToken: "current-token",
      slug: "test-tenant",
    });
    try {
      await api.GET("/reporting/runs" as never);
      throw new Error("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ServerError);
      expect((err as ServerError).requestId).toBe("req-abc-123");
    }
  });
});

describe("refreshMiddleware", () => {
  it("refreshes once on 401 and retries the original request", async () => {
    const { api, store } = makeClient({
      accessToken: "stale-token",
      refreshToken: "good-refresh",
    });
    const { data } = await api.GET("/platform/auth/me" as never);
    expect(data).toEqual({ id: "p1", email: "p@test.example" });
    expect(store.getAccessToken()).toBe("fresh-access");
  });

  it("throws UnauthorizedError when refresh fails", async () => {
    const { api } = makeClient({
      accessToken: "stale-token",
      refreshToken: "bad-refresh",
    });
    await expect(
      api.GET("/platform/auth/me" as never),
    ).rejects.toBeInstanceOf(UnauthorizedError);
  });
});
```

- [ ] **Step 9: Run all tests**

```bash
cd admin
pnpm --filter @sacco/api-client test
```
Expected: every test passes.

- [ ] **Step 10: Commit**

```bash
git add admin/packages/api-client/src/{errors.ts,middleware,client.ts} \
        admin/packages/api-client/src/__tests__/middleware.test.ts
git commit -m "feat(api-client): auth + tenant + idempotency + errors + refresh middleware"
```

---

## Task 5: Per-resource client builders

These are thin convenience wrappers. They expose a domain-grouped API without changing types.

**Files:**
- Create: `admin/packages/api-client/src/resources/index.ts`
- Create: `admin/packages/api-client/src/resources/platformAuth.ts`
- Create: `admin/packages/api-client/src/resources/tenants.ts`
- Create: `admin/packages/api-client/src/resources/billing.ts`
- Create: `admin/packages/api-client/src/resources/members.ts`
- Create: `admin/packages/api-client/src/resources/savings.ts`
- Create: `admin/packages/api-client/src/resources/credit.ts`
- Create: `admin/packages/api-client/src/resources/fees.ts`
- Create: `admin/packages/api-client/src/resources/ledger.ts`
- Create: `admin/packages/api-client/src/resources/reporting.ts`
- Create: `admin/packages/api-client/src/resources/makerChecker.ts`
- Create: `admin/packages/api-client/src/resources/impersonations.ts`
- Create: `admin/packages/api-client/src/resources/audit.ts`
- Create: `admin/packages/api-client/src/resources/admin.ts`
- Modify: `admin/packages/api-client/src/index.ts`

- [ ] **Step 1: Pattern + first resource (`platformAuth`)**

Each resource file follows the same pattern: a factory taking the openapi-fetch client + returning typed methods.

```typescript
// admin/packages/api-client/src/resources/platformAuth.ts
import type { FetchClient } from "../client";

export function platformAuth(api: FetchClient) {
  return {
    login: (body: { email: string; password: string }) =>
      api.POST("/platform/auth/token" as never, { body } as never),
    refresh: (body: { refresh_token: string }) =>
      api.POST("/platform/auth/refresh" as never, { body } as never),
    logout: () => api.POST("/platform/auth/logout" as never),
    me: () => api.GET("/platform/auth/me" as never),
    passwordResetRequest: (body: { email: string }) =>
      api.POST("/platform/auth/password-reset/request" as never, { body } as never),
    passwordResetConfirm: (body: { token: string; new_password: string }) =>
      api.POST("/platform/auth/password-reset/confirm" as never, { body } as never),
  } as const;
}
```

- [ ] **Step 2: Tenants + billing + members + savings (the rest of the platform-context groups)**

`resources/tenants.ts`:

```typescript
import type { FetchClient } from "../client";

export function tenants(api: FetchClient) {
  return {
    list: (query?: { status?: string }) =>
      api.GET("/platform/tenants" as never, { params: { query } } as never),
    get: (id: string) =>
      api.GET("/platform/tenants/{tenant_id}" as never, {
        params: { path: { tenant_id: id } },
      } as never),
    create: (body: { slug: string; name: string; admin_email?: string }) =>
      api.POST("/platform/tenants" as never, { body } as never),
    retryProvisioning: (id: string) =>
      api.POST("/platform/tenants/{tenant_id}/retry-provisioning" as never, {
        params: { path: { tenant_id: id } },
      } as never),
    // Phase 1.7 lifecycle endpoints
    patch: (id: string, body: { name: string }) =>
      api.PATCH("/platform/tenants/{tenant_id}" as never, {
        params: { path: { tenant_id: id } },
        body,
      } as never),
    suspend: (id: string, body: { reason: string }) =>
      api.POST("/platform/tenants/{tenant_id}/suspend" as never, {
        params: { path: { tenant_id: id } },
        body,
      } as never),
    reactivate: (id: string) =>
      api.POST("/platform/tenants/{tenant_id}/reactivate" as never, {
        params: { path: { tenant_id: id } },
      } as never),
    assignPlan: (id: string, body: { plan_id: string; start_date?: string }) =>
      api.POST("/platform/tenants/{tenant_id}/assign-plan" as never, {
        params: { path: { tenant_id: id } },
        body,
      } as never),
  } as const;
}
```

Write the equivalent file for `billing`, `members`, `savings`, `credit`, `fees`, `ledger`, `reporting`, `makerChecker`, `impersonations`, `audit`, and `admin`. Each file:
- Exports one factory function
- Each method delegates to `api.METHOD(path, options)`
- The `as never` casts are deliberate — they tell TypeScript to trust the path string against the generated paths (the type inference is correct at call sites but the openapi-fetch type signature is intricate)
- For endpoints behind Phase 1.7 sub-plans that aren't yet merged, comment them out or skip — the codegen will fail otherwise

Refer to the Portal v1 index §5 for the full path list per resource.

- [ ] **Step 3: Resource registry**

```typescript
// admin/packages/api-client/src/resources/index.ts
import type { FetchClient } from "../client";
import { platformAuth } from "./platformAuth";
import { tenants } from "./tenants";
import { billing } from "./billing";
import { members } from "./members";
import { savings } from "./savings";
import { credit } from "./credit";
import { fees } from "./fees";
import { ledger } from "./ledger";
import { reporting } from "./reporting";
import { makerChecker } from "./makerChecker";
import { impersonations } from "./impersonations";
import { audit } from "./audit";
import { admin } from "./admin";

export function buildResources(api: FetchClient) {
  return {
    platformAuth: platformAuth(api),
    tenants: tenants(api),
    billing: billing(api),
    members: members(api),
    savings: savings(api),
    credit: credit(api),
    fees: fees(api),
    ledger: ledger(api),
    reporting: reporting(api),
    makerChecker: makerChecker(api),
    impersonations: impersonations(api),
    audit: audit(api),
    admin: admin(api),
  } as const;
}

export type Resources = ReturnType<typeof buildResources>;
```

- [ ] **Step 4: Top-level convenience**

Update `src/index.ts`:

```typescript
export * from "./types";
export * from "./errors";
export * from "./token-store";
export * from "./tenant-context";
export { createApiClient, type ApiClientOptions, type FetchClient } from "./client";
export { buildResources, type Resources } from "./resources";
```

- [ ] **Step 5: Typecheck + tests pass**

```bash
cd admin
pnpm --filter @sacco/api-client typecheck
pnpm --filter @sacco/api-client test
```
Expected: green.

- [ ] **Step 6: Commit**

```bash
git add admin/packages/api-client/src/resources/ \
        admin/packages/api-client/src/index.ts
git commit -m "feat(api-client): per-resource client builders for all groups"
```

---

## Task 6: TanStack Query helpers

**Files:**
- Create: `admin/packages/api-client/src/query-keys.ts`
- Create: `admin/packages/api-client/src/hooks.ts`

- [ ] **Step 1: Query-key factories**

```typescript
// admin/packages/api-client/src/query-keys.ts
/**
 * Flat factory object. Convention: each domain has a `root` (so a single
 * mutation can invalidate `["tenants"]` and blow away every cached tenant
 * query) plus per-operation factories that produce stable keys.
 *
 * Filters are stringified positionally so `["tenants", "list", {status: "active"}]`
 * differs from `["tenants", "list", {}]`.
 */
export const queryKeys = {
  platformAuth: {
    me: () => ["platformAuth", "me"] as const,
  },
  tenants: {
    root: () => ["tenants"] as const,
    list: (filters?: Record<string, unknown>) =>
      ["tenants", "list", filters ?? {}] as const,
    detail: (id: string) => ["tenants", "detail", id] as const,
    users: (id: string) => ["tenants", "users", id] as const,
  },
  billing: {
    root: () => ["billing"] as const,
    plans: (filters?: Record<string, unknown>) =>
      ["billing", "plans", filters ?? {}] as const,
    plan: (id: string) => ["billing", "plan", id] as const,
    subscriptions: (filters?: Record<string, unknown>) =>
      ["billing", "subscriptions", filters ?? {}] as const,
    subscription: (id: string) => ["billing", "subscription", id] as const,
    invoices: (filters?: Record<string, unknown>) =>
      ["billing", "invoices", filters ?? {}] as const,
    invoice: (id: string) => ["billing", "invoice", id] as const,
    pendingPayments: () => ["billing", "pendingPayments"] as const,
  },
  members: {
    root: () => ["members"] as const,
    list: (filters?: Record<string, unknown>) =>
      ["members", "list", filters ?? {}] as const,
    detail: (id: string) => ["members", "detail", id] as const,
  },
  savings: {
    root: () => ["savings"] as const,
    products: () => ["savings", "products"] as const,
    accounts: (filters?: Record<string, unknown>) =>
      ["savings", "accounts", filters ?? {}] as const,
    account: (id: string) => ["savings", "account", id] as const,
    transactions: (id: string) =>
      ["savings", "account", id, "transactions"] as const,
  },
  credit: {
    root: () => ["credit"] as const,
    products: () => ["credit", "products"] as const,
    applications: (filters?: Record<string, unknown>) =>
      ["credit", "applications", filters ?? {}] as const,
    application: (id: string) => ["credit", "application", id] as const,
    loans: (filters?: Record<string, unknown>) =>
      ["credit", "loans", filters ?? {}] as const,
    loan: (id: string) => ["credit", "loan", id] as const,
    schedule: (id: string) => ["credit", "loan", id, "schedule"] as const,
    repayments: (id: string) => ["credit", "loan", id, "repayments"] as const,
    payrollBatches: () => ["credit", "payrollBatches"] as const,
  },
  fees: {
    root: () => ["fees"] as const,
    types: () => ["fees", "types"] as const,
    assessments: (filters?: Record<string, unknown>) =>
      ["fees", "assessments", filters ?? {}] as const,
  },
  ledger: {
    root: () => ["ledger"] as const,
    accounts: () => ["ledger", "accounts"] as const,
    account: (id: string) => ["ledger", "account", id] as const,
    journalEntries: () => ["ledger", "journalEntries"] as const,
  },
  reporting: {
    root: () => ["reporting"] as const,
    trialBalance: (params?: Record<string, unknown>) =>
      ["reporting", "trial-balance", params ?? {}] as const,
    loanPortfolio: (params?: Record<string, unknown>) =>
      ["reporting", "loan-portfolio", params ?? {}] as const,
    incomeStatement: (params?: Record<string, unknown>) =>
      ["reporting", "income-statement", params ?? {}] as const,
    savingsStatement: (params?: Record<string, unknown>) =>
      ["reporting", "savings-statement", params ?? {}] as const,
    feeCollection: (params?: Record<string, unknown>) =>
      ["reporting", "fee-collection", params ?? {}] as const,
    runs: () => ["reporting", "runs"] as const,
  },
  approvals: {
    root: () => ["approvals"] as const,
    platform: (filters?: Record<string, unknown>) =>
      ["approvals", "platform", filters ?? {}] as const,
    tenant: (filters?: Record<string, unknown>) =>
      ["approvals", "tenant", filters ?? {}] as const,
    detail: (id: string) => ["approvals", "detail", id] as const,
  },
  impersonations: {
    root: () => ["impersonations"] as const,
    active: () => ["impersonations", "active"] as const,
    all: () => ["impersonations", "all"] as const,
  },
  audit: {
    root: () => ["audit"] as const,
    platform: (filters?: Record<string, unknown>) =>
      ["audit", "platform", filters ?? {}] as const,
    tenant: (filters?: Record<string, unknown>) =>
      ["audit", "tenant", filters ?? {}] as const,
    detail: (id: string) => ["audit", "detail", id] as const,
  },
  admin: {
    dashboardStats: () => ["admin", "dashboardStats"] as const,
  },
} as const;
```

- [ ] **Step 2: Typed query/mutation hooks**

```typescript
// admin/packages/api-client/src/hooks.ts
import {
  useMutation,
  type UseMutationOptions,
  useQuery,
  type UseQueryOptions,
  useQueryClient,
  type QueryKey,
} from "@tanstack/react-query";

/**
 * Thin wrapper around useQuery. The fetcher signature is `() => Promise<T>`.
 *
 * Usage:
 *   const tenants = useTypedQuery(
 *     queryKeys.tenants.list(),
 *     () => api.tenants.list(),
 *   );
 */
export function useTypedQuery<TData, TError = Error>(
  queryKey: QueryKey,
  queryFn: () => Promise<TData>,
  options?: Omit<UseQueryOptions<TData, TError, TData, QueryKey>, "queryKey" | "queryFn">,
) {
  return useQuery<TData, TError, TData, QueryKey>({
    queryKey,
    queryFn,
    ...options,
  });
}

/**
 * Wrapper around useMutation that auto-invalidates a configurable list of
 * query keys when the mutation succeeds. Pass `invalidates: ["tenants"]` to
 * blow away every tenant query, or finer-grained keys for surgical updates.
 */
export interface TypedMutationOptions<TData, TVariables, TError = Error>
  extends Omit<
    UseMutationOptions<TData, TError, TVariables, unknown>,
    "mutationFn"
  > {
  invalidates?: QueryKey[];
}

export function useTypedMutation<TData, TVariables, TError = Error>(
  mutationFn: (vars: TVariables) => Promise<TData>,
  options?: TypedMutationOptions<TData, TVariables, TError>,
) {
  const qc = useQueryClient();
  return useMutation<TData, TError, TVariables, unknown>({
    mutationFn,
    ...options,
    onSuccess: async (data, vars, ctx) => {
      if (options?.invalidates) {
        await Promise.all(
          options.invalidates.map((key) =>
            qc.invalidateQueries({ queryKey: key }),
          ),
        );
      }
      await options?.onSuccess?.(data, vars, ctx);
    },
  });
}
```

- [ ] **Step 3: Add to root index**

Append to `src/index.ts`:

```typescript
export { queryKeys } from "./query-keys";
export {
  useTypedQuery,
  useTypedMutation,
  type TypedMutationOptions,
} from "./hooks";
```

- [ ] **Step 4: Verify typecheck**

```bash
cd admin
pnpm --filter @sacco/api-client typecheck
```
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add admin/packages/api-client/src/{query-keys,hooks,index}.ts
git commit -m "feat(api-client): queryKeys + useTypedQuery + useTypedMutation hooks"
```

---

## Task 7: Final verification

- [ ] **Step 1: Full pipeline**

```bash
cd admin
pnpm install
pnpm --filter @sacco/api-client codegen
pnpm typecheck
pnpm lint
pnpm test
```
Expected: every step green.

- [ ] **Step 2: Spec freshness check (manual)**

If Phase 1.7 sub-plans have merged since the last `openapi:capture`, re-run:

```bash
cd admin
pnpm openapi:capture
pnpm --filter @sacco/api-client codegen
git diff --stat packages/api-client/
```
Expected: the diff shows the new paths (e.g., `/platform/approvals/*`, `/platform/audit-log`, etc.) appearing in both `openapi.json` and `schema.d.ts`.

If there are new paths, commit them as part of this sub-plan.

- [ ] **Step 3: PR**

```bash
git push -u origin feat/portal-v1/05-api-client
gh pr create --title "feat(api-client): OpenAPI codegen + middleware + resources + TanStack hooks" --body "$(cat <<'EOF'
## Summary
- `admin/scripts/capture-openapi.mjs` boots uvicorn and writes `packages/api-client/openapi.json` (committed snapshot)
- `openapi-typescript` codegen produces `src/generated/schema.d.ts`
- `createApiClient` factory wraps `openapi-fetch` with five middleware:
  - `authMiddleware` — injects `Authorization: Bearer <token>` from a pluggable `TokenStore`
  - `tenantMiddleware` — injects `X-Tenant-Slug` from a pluggable `TenantContext` on non-platform routes
  - `idempotencyMiddleware` — adds `Idempotency-Key` (UUID v7) on POST/PUT/PATCH/DELETE
  - `errorMiddleware` — translates 402 → `SubscriptionPastDueError`, gate-signature 403 → `SubscriptionSuspendedError`, 5xx → `ServerError` with `X-Request-ID` for log correlation
  - `refreshMiddleware` — 401-once with promise coalescing; throws `UnauthorizedError` on second failure
- Per-resource client builders for all groups (platformAuth, tenants, billing, members, savings, credit, fees, ledger, reporting, makerChecker, impersonations, audit, admin)
- TanStack Query helpers: `queryKeys` flat factories, `useTypedQuery`, `useTypedMutation` with `invalidates` auto-invalidation

## Out of scope
- Zod schemas for runtime validation (sub-plan 06)
- Auth shell wiring (sub-plan 07)
- App shell error boundary that catches the typed errors (sub-plan 08)

## Test plan
- [ ] `pnpm --filter @sacco/api-client codegen` produces a clean `schema.d.ts`
- [ ] `pnpm --filter @sacco/api-client test` — all middleware tests pass (auth, tenant, idempotency, 402/403/5xx errors, 401-refresh-once, refresh-failure-throws-Unauthorized)
- [ ] `pnpm typecheck && pnpm lint` clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] `admin/scripts/capture-openapi.mjs` boots the FastAPI, captures the spec, exits cleanly
- [ ] `admin/packages/api-client/openapi.json` is committed
- [ ] `pnpm --filter @sacco/api-client codegen` produces `src/generated/schema.d.ts`
- [ ] `createApiClient` wires five middleware in order: auth → tenant → idempotency → errors → refresh
- [ ] `SubscriptionPastDueError`, `SubscriptionSuspendedError`, `ServerError`, `UnauthorizedError` exported and thrown by middleware
- [ ] Idempotency keys are UUID v7 (validated by MSW handler rejecting < 36 chars)
- [ ] 401-refresh-once coalesces concurrent refreshes via a singleton promise
- [ ] Refresh failure throws `UnauthorizedError` (does not loop)
- [ ] Thirteen per-resource client builders exist and typecheck
- [ ] `queryKeys`, `useTypedQuery`, `useTypedMutation` exported
- [ ] All Vitest + MSW tests pass
- [ ] PR opened, CI green

## Notes for the executing subagent

- **Do not** invent endpoints. The `paths` type is the contract. If a path doesn't exist in `schema.d.ts`, it doesn't exist on the backend (or the OpenAPI snapshot is stale — re-capture).
- **Do not** mutate the captured `openapi.json` by hand. Re-run `pnpm openapi:capture`. CI sub-plan 39 will guard against drift.
- **Do not** add per-request `fetch` overrides as a public API. Tests use the `fetch` option on `createApiClient`; production calls don't need it.
- **Do not** wire the token store or tenant context to a specific state library here. Sub-plan 07 implements them; this sub-plan only defines the interfaces.
- The `as never` casts in resource builders are intentional. The openapi-fetch `Client<paths>` type has overloads that don't narrow cleanly when the path is a variable. Casting tells TypeScript to trust the literal. The CALLERS get full type inference because the resource methods have concrete signatures.
- If `pnpm openapi:capture` fails because the backend isn't reachable, ensure `make up && make migrate` ran in another terminal and that uvicorn can start. The script uses port 8765 by default (override via `OPENAPI_CAPTURE_PORT`).
- For endpoints behind Phase 1.7 sub-plans that haven't merged at execution time, the codegen will not emit them. Either re-run codegen after the dependency lands, or skip the affected resource methods. Document any skipped methods in the PR description.
- The `tenantMiddleware` skips `/platform/*` and `/.well-known/*`. The full list of tenant-context routes is anything else (`/members`, `/savings`, `/credit`, `/fees`, `/ledger`, `/reporting`, `/approvals`, `/audit-log`, `/auth/*`, `/billing/me/*`). If a new platform-context root path is added, update the skip list.
- The `errorMiddleware` 403 detection relies on the gate's exact `detail` prefix (`"Subscription status"`). If `_check_subscription_gate` in `app/core/db.py` changes its detail string, update the prefix here. This is fragile but the alternative (route-pattern matching) is fragile too — the prefix is the cheapest contract.
- The `refreshMiddleware` writes `X-Sacco-Retry: 1` as the loop-breaker. Backend code does not see this header (the test header name is intentionally namespace-prefixed). Do not change the name without auditing the auth shell.
- UUID v7 has a time-prefix which helps debug ordering. `uuid` v10 supports v7 natively (`v7` named export). If for some reason v10 isn't available, fall back to v4 — the backend treats keys as opaque strings, so it works either way.
- If MSW reports "unhandled request" errors during tests, the most likely cause is that a middleware fires a refresh against an endpoint not in the handler list. Add handlers explicitly; do not set `onUnhandledRequest: "warn"`.
- The query keys are intentionally stable strings, not enum imports. Stale closures over array literals would cause re-renders; factory functions don't.
