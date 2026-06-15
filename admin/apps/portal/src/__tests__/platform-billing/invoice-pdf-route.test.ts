// admin/apps/portal/src/__tests__/platform-billing/invoice-pdf-route.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getServerAccessToken = vi.fn();
vi.mock("@/auth/server-helpers", () => ({
  getServerAccessToken: (...a: unknown[]) => getServerAccessToken(...a),
}));

const fetchMock = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function ctx(id: string) {
  return { params: Promise.resolve({ id }) };
}

describe("GET /api/billing/invoices/[id]/pdf", () => {
  it("401s without a platform session", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: null });
    const { GET } = await import("../../../app/api/billing/invoices/[id]/pdf/route");
    const res = await GET(new Request("http://localhost/api/billing/invoices/i1/pdf"), ctx("i1"));
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("proxies the PDF with the platform bearer and application/pdf", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "plat-access" });
    fetchMock.mockResolvedValue({
      ok: true, status: 200,
      arrayBuffer: async () => new Uint8Array([37, 80, 68, 70]).buffer, // %PDF
    });
    const { GET } = await import("../../../app/api/billing/invoices/[id]/pdf/route");
    const res = await GET(new Request("http://localhost/api/billing/invoices/i1/pdf"), ctx("i1"));
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("application/pdf");
    const [url, init] = fetchMock.mock.calls[0] as [string, { headers?: Record<string, string> }];
    expect(String(url)).toContain("/platform/billing/invoices/i1.pdf");
    expect(init.headers?.["Authorization"]).toBe("Bearer plat-access");
  });

  it("propagates a non-ok status", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "plat-access" });
    fetchMock.mockResolvedValue({ ok: false, status: 404, arrayBuffer: async () => new ArrayBuffer(0) });
    const { GET } = await import("../../../app/api/billing/invoices/[id]/pdf/route");
    const res = await GET(new Request("http://localhost/api/billing/invoices/x/pdf"), ctx("x"));
    expect(res.status).toBe(404);
  });
});
