// admin/apps/portal/src/__tests__/tenant-reports/reporting-download-route.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getServerAccessToken = vi.fn();
const getServerTenantSlug = vi.fn();
vi.mock("@/auth/server-helpers", () => ({
  getServerAccessToken: (...a: unknown[]) => getServerAccessToken(...a),
  getServerTenantSlug: (...a: unknown[]) => getServerTenantSlug(...a),
}));

const fetchMock = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const ctx = (report: string) => ({ params: Promise.resolve({ report }) });

describe("GET /api/reporting/[report]", () => {
  it("401s without a tenant session", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: null });
    getServerTenantSlug.mockResolvedValue("alpha");
    const { GET } = await import("../../../app/api/reporting/[report]/route");
    const res = await GET(
      new Request("http://localhost/api/reporting/trial-balance?format=csv"),
      ctx("trial-balance"),
    );
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("404s an unknown report", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "t" });
    getServerTenantSlug.mockResolvedValue("alpha");
    const { GET } = await import("../../../app/api/reporting/[report]/route");
    const res = await GET(
      new Request("http://localhost/api/reporting/bogus?format=csv"),
      ctx("bogus"),
    );
    expect(res.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("proxies a known report with bearer + slug + query", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "tenant-access" });
    getServerTenantSlug.mockResolvedValue("alpha");
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      arrayBuffer: async () => new Uint8Array([1, 2]).buffer,
      headers: new Headers({
        "content-type": "text/csv",
        "content-disposition": 'attachment; filename="trial-balance.csv"',
      }),
    });
    const { GET } = await import("../../../app/api/reporting/[report]/route");
    const res = await GET(
      new Request(
        "http://localhost/api/reporting/loan-portfolio?format=csv&as_of=2026-06-01&status=disbursed",
      ),
      ctx("loan-portfolio"),
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("text/csv");
    const [url, init] = fetchMock.mock.calls[0] as [
      string,
      { headers?: Record<string, string> },
    ];
    expect(String(url)).toContain("/reporting/loan-portfolio?");
    expect(String(url)).toContain("format=csv");
    expect(String(url)).toContain("as_of=2026-06-01");
    expect(String(url)).toContain("status=disbursed");
    expect(init.headers?.["Authorization"]).toBe("Bearer tenant-access");
    expect(init.headers?.["X-Tenant-Slug"]).toBe("alpha");
  });
});
