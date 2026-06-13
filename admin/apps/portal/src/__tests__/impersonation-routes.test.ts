import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getServerAccessToken = vi.fn();
vi.mock("@/auth/server-helpers", () => ({
  getServerAccessToken: (...a: unknown[]) => getServerAccessToken(...a),
}));

const setRefreshCookie = vi.fn();
const setTenantSlugCookie = vi.fn();
const setImpersonationCookie = vi.fn();
const clearRefreshCookie = vi.fn();
const clearTenantSlugCookie = vi.fn();
const clearImpersonationCookie = vi.fn();
vi.mock("@/auth/cookies", () => ({
  TENANT_REFRESH_COOKIE: "sacco_refresh_tenant",
  TENANT_REFRESH_MAX_AGE: 28800,
  setRefreshCookie: (...a: unknown[]) => setRefreshCookie(...a),
  setTenantSlugCookie: (...a: unknown[]) => setTenantSlugCookie(...a),
  setImpersonationCookie: (...a: unknown[]) => setImpersonationCookie(...a),
  clearRefreshCookie: (...a: unknown[]) => clearRefreshCookie(...a),
  clearTenantSlugCookie: (...a: unknown[]) => clearTenantSlugCookie(...a),
  clearImpersonationCookie: (...a: unknown[]) => clearImpersonationCookie(...a),
}));

const fetchMock = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function req(body: unknown): Request {
  return new Request("http://localhost/api/impersonation/activate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

describe("POST /api/impersonation/activate", () => {
  it("401s when there is no platform session", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: null });
    const { POST } = await import("../../app/api/impersonation/activate/route");
    const res = await POST(req({ impersonation_id: "imp1", tenant_id: "t1", tenant_name: "Alpha" }));
    expect(res.status).toBe(401);
    expect(setRefreshCookie).not.toHaveBeenCalled();
  });

  it("mints, sets tenant cookies, and returns the access token", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "plat-access" });
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        access_token: "tenant-access",
        refresh_token: "tenant-refresh",
        expires_in: 900,
        tenant_slug: "alpha",
        impersonation_id: "imp1",
        impersonation_expires_at: "2026-06-13T12:30:00Z",
      }),
    });
    const { POST } = await import("../../app/api/impersonation/activate/route");
    const res = await POST(req({ impersonation_id: "imp1", tenant_id: "t1", tenant_name: "Alpha SACCO" }));
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ access_token: "tenant-access", tenant_slug: "alpha" });
    // platform bearer used to mint
    const [url, init] = fetchMock.mock.calls[0] as [
      string,
      { method?: string; headers?: Record<string, string> },
    ];
    expect(String(url)).toContain("/platform/impersonations/imp1/mint-tenant-token");
    expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer plat-access");
    // tenant cookies set
    expect(setRefreshCookie).toHaveBeenCalledWith(
      expect.objectContaining({ name: "sacco_refresh_tenant", value: "tenant-refresh" }),
    );
    expect(setTenantSlugCookie).toHaveBeenCalledWith("alpha");
    expect(setImpersonationCookie).toHaveBeenCalledWith(
      expect.objectContaining({ id: "imp1", tenantId: "t1", tenantName: "Alpha SACCO", expiresAt: "2026-06-13T12:30:00Z" }),
    );
  });

  it("propagates the mint error status (e.g. 409 not yet approved)", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "plat-access" });
    fetchMock.mockResolvedValue({
      ok: false, status: 409, json: async () => ({ detail: "not yet active" }),
    });
    const { POST } = await import("../../app/api/impersonation/activate/route");
    const res = await POST(req({ impersonation_id: "imp1", tenant_id: "t1", tenant_name: "Alpha" }));
    expect(res.status).toBe(409);
    expect(setRefreshCookie).not.toHaveBeenCalled();
  });
});

describe("POST /api/impersonation/end", () => {
  it("ends the impersonation and clears tenant cookies", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "plat-access" });
    fetchMock.mockResolvedValue({ ok: true, status: 204, json: async () => ({}) });
    const { POST } = await import("../../app/api/impersonation/end/route");
    const res = await POST(
      new Request("http://localhost/api/impersonation/end", {
        method: "POST",
        body: JSON.stringify({ impersonation_id: "imp1" }),
      }),
    );
    expect(res.status).toBe(200);
    const [url, init] = fetchMock.mock.calls[0] as [
      string,
      { method?: string; headers?: Record<string, string> },
    ];
    expect(String(url)).toContain("/platform/impersonations/imp1");
    expect(init.method).toBe("DELETE");
    expect(clearRefreshCookie).toHaveBeenCalled();
    expect(clearTenantSlugCookie).toHaveBeenCalled();
    expect(clearImpersonationCookie).toHaveBeenCalled();
  });
});
