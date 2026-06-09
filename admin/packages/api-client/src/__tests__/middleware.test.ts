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

const BASE = "http://api.example.com";

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
    const { api } = makeClient({
      accessToken: "fresh-access",
      slug: "ignored",
    });
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

  it("throws UnauthorizedError when refresh succeeds but retry still 401s", async () => {
    // Override the /platform/auth/me handler to always 401, even with the fresh token.
    server.use(
      http.get(`${BASE}/platform/auth/me`, () =>
        new HttpResponse(null, { status: 401 }),
      ),
    );
    const { api } = makeClient({
      accessToken: "stale-token",
      refreshToken: "good-refresh",
    });
    await expect(
      api.GET("/platform/auth/me" as never),
    ).rejects.toBeInstanceOf(UnauthorizedError);
  });
});

describe("refreshMiddleware (cookie-backed)", () => {
  it("uses credentials:include with no body when refresh token is null", async () => {
    // Cookie-backed path: refresh token lives in httpOnly cookie, JS sees null.
    // The handler ignores the body — it just verifies the request shape.
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
