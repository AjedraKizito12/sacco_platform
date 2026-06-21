// admin/apps/portal/src/__tests__/tenant-credit/statement-pdf-route.test.ts
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

const ctx = (id: string) => ({ params: Promise.resolve({ id }) });

describe("GET /api/credit/loans/[id]/statement-pdf", () => {
  it("401s without a tenant session", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: null });
    getServerTenantSlug.mockResolvedValue("alpha");
    const { GET } = await import("../../../app/api/credit/loans/[id]/statement-pdf/route");
    const res = await GET(
      new Request("http://localhost/api/credit/loans/l1/statement-pdf"),
      ctx("l1"),
    );
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("proxies with the tenant bearer + X-Tenant-Slug", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "tenant-access" });
    getServerTenantSlug.mockResolvedValue("alpha");
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      arrayBuffer: async () => new Uint8Array([37, 80, 68, 70]).buffer,
    });
    const { GET } = await import("../../../app/api/credit/loans/[id]/statement-pdf/route");
    const res = await GET(
      new Request("http://localhost/api/credit/loans/l1/statement-pdf"),
      ctx("l1"),
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("application/pdf");
    const [url, init] = fetchMock.mock.calls[0] as [
      string,
      { headers?: Record<string, string> },
    ];
    expect(String(url)).toContain("/credit/loans/l1/statement.pdf");
    expect(init.headers?.["Authorization"]).toBe("Bearer tenant-access");
    expect(init.headers?.["X-Tenant-Slug"]).toBe("alpha");
  });
});
