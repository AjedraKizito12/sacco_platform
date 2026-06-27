// admin/apps/portal/src/__tests__/member-login-route.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const setRefreshCookie = vi.fn();
const setTenantSlugCookie = vi.fn();
const getTenantSlugCookie = vi.fn();
vi.mock("@/auth/cookies", () => ({
  MEMBER_REFRESH_COOKIE: "sacco_refresh_member",
  MEMBER_REFRESH_MAX_AGE: 28800,
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
  return new Request("http://localhost/api/auth/member-login", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

const creds = { email: "jane@example.com", password: "e2e-Password-123!" };

function okBackend() {
  fetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      access_token: "member-access",
      refresh_token: "member-refresh",
      expires_in: 900,
    }),
  });
}

describe("POST /api/auth/member-login", () => {
  it("posts to /member/auth/token and sets the member refresh cookie", async () => {
    okBackend();
    const { POST } = await import("../../app/api/auth/member-login/route");
    const res = await POST(req(creds, { "x-sacco-tenant-slug": "acme" }));
    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [
      string,
      { headers: Record<string, string> },
    ];
    expect(url).toContain("/member/auth/token");
    expect(init.headers["X-Tenant-Slug"]).toBe("acme");
    expect(setRefreshCookie).toHaveBeenCalledWith(
      expect.objectContaining({ name: "sacco_refresh_member" }),
    );
    expect(getTenantSlugCookie).not.toHaveBeenCalled();
  });

  it("falls back to the sacco_tenant_slug cookie when the header is absent", async () => {
    getTenantSlugCookie.mockResolvedValue("beta");
    okBackend();
    const { POST } = await import("../../app/api/auth/member-login/route");
    const res = await POST(req(creds));
    expect(res.status).toBe(200);
    const [, init] = fetchMock.mock.calls[0] as [
      string,
      { headers: Record<string, string> },
    ];
    expect(init.headers["X-Tenant-Slug"]).toBe("beta");
  });

  it("400s when the body is invalid", async () => {
    const { POST } = await import("../../app/api/auth/member-login/route");
    const res = await POST(req({ email: "not-an-email" }));
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("400s when neither header nor cookie provide a slug", async () => {
    getTenantSlugCookie.mockResolvedValue(null);
    const { POST } = await import("../../app/api/auth/member-login/route");
    const res = await POST(req(creds));
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("passes through an upstream error status", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: "Invalid credentials" }),
    });
    const { POST } = await import("../../app/api/auth/member-login/route");
    const res = await POST(req(creds, { "x-sacco-tenant-slug": "acme" }));
    expect(res.status).toBe(401);
  });
});
