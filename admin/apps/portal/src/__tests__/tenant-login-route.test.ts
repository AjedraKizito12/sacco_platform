// admin/apps/portal/src/__tests__/tenant-login-route.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const setRefreshCookie = vi.fn();
const setTenantSlugCookie = vi.fn();
const getTenantSlugCookie = vi.fn();
vi.mock("@/auth/cookies", () => ({
  TENANT_REFRESH_COOKIE: "sacco_refresh_tenant",
  TENANT_REFRESH_MAX_AGE: 28800,
  setRefreshCookie: (...a: unknown[]) => setRefreshCookie(...a),
  setTenantSlugCookie: (...a: unknown[]) => setTenantSlugCookie(...a),
  getTenantSlugCookie: (...a: unknown[]) => getTenantSlugCookie(...a),
}));

const fetchMock = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("fetch", fetchMock);
  getTenantSlugCookie.mockResolvedValue(null);
});
afterEach(() => vi.unstubAllGlobals());

function req(body: unknown, headers: Record<string, string> = {}): Request {
  return new Request("http://localhost/api/auth/tenant-login", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

const creds = { email: "ops@saccodemo.com", password: "e2e-Password-123!" };

function okBackend() {
  fetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      access_token: "tenant-access",
      refresh_token: "tenant-refresh",
      expires_in: 900,
    }),
  });
}

describe("POST /api/auth/tenant-login", () => {
  it("uses the x-sacco-tenant-slug header when present", async () => {
    okBackend();
    const { POST } = await import("../../app/api/auth/tenant-login/route");
    const res = await POST(req(creds, { "x-sacco-tenant-slug": "acme" }));
    expect(res.status).toBe(200);
    const [, init] = fetchMock.mock.calls[0] as [string, { headers: Record<string, string> }];
    expect(init.headers["X-Tenant-Slug"]).toBe("acme");
    expect(setRefreshCookie).toHaveBeenCalled();
    expect(getTenantSlugCookie).not.toHaveBeenCalled();
  });

  it("falls back to the sacco_tenant_slug cookie when the header is absent", async () => {
    getTenantSlugCookie.mockResolvedValue("beta");
    okBackend();
    const { POST } = await import("../../app/api/auth/tenant-login/route");
    const res = await POST(req(creds));
    expect(res.status).toBe(200);
    const [, init] = fetchMock.mock.calls[0] as [string, { headers: Record<string, string> }];
    expect(init.headers["X-Tenant-Slug"]).toBe("beta");
  });

  it("400s when neither header nor cookie provide a slug", async () => {
    getTenantSlugCookie.mockResolvedValue(null);
    const { POST } = await import("../../app/api/auth/tenant-login/route");
    const res = await POST(req(creds));
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
