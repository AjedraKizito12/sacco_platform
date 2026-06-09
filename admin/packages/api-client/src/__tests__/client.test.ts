// admin/packages/api-client/src/__tests__/client.test.ts
import { describe, expect, it, beforeAll, afterAll, afterEach } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { createApiClient } from "../client";
import { InMemoryTokenStore } from "../token-store";
import { FixedTenantContext } from "../tenant-context";

const server = setupServer(
  http.get("http://api.example.com/healthz", () =>
    HttpResponse.json({ status: "ok" }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("createApiClient (base)", () => {
  it("issues a GET against the configured base URL", async () => {
    const api = createApiClient({
      baseUrl: "http://api.example.com",
      tokenStore: new InMemoryTokenStore("/platform/auth/refresh"),
      tenantContext: new FixedTenantContext(null),
    });
    const { data } = await api.GET("/healthz" as never);
    expect(data).toEqual({ status: "ok" });
  });
});
