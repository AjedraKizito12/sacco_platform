// admin/apps/portal/src/__tests__/tenant-billing/tenant-page-context.test.ts
import { describe, expect, it, vi, beforeEach } from "vitest";

const redirect = vi.fn((url: string) => {
  throw new Error(`REDIRECT:${url}`);
});
vi.mock("next/navigation", () => ({ redirect: (u: string) => redirect(u) }));

const getServerAccessToken = vi.fn();
const getServerCurrentUser = vi.fn();
const getServerTenantSlug = vi.fn();
vi.mock("@/auth/server-helpers", () => ({
  getServerAccessToken: (...a: unknown[]) => getServerAccessToken(...a),
  getServerCurrentUser: (...a: unknown[]) => getServerCurrentUser(...a),
  getServerTenantSlug: (...a: unknown[]) => getServerTenantSlug(...a),
}));

import { getTenantPageContext } from "../../auth/server-page-context";

describe("getTenantPageContext", () => {
  beforeEach(() => vi.clearAllMocks());

  it("redirects to /login when there is no tenant access token", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: null });
    getServerTenantSlug.mockResolvedValue("alpha");
    await expect(getTenantPageContext()).rejects.toThrow("REDIRECT:/login");
  });

  it("redirects to /login when /me fails", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "ta" });
    getServerTenantSlug.mockResolvedValue("alpha");
    getServerCurrentUser.mockResolvedValue(null);
    await expect(getTenantPageContext()).rejects.toThrow("REDIRECT:/login");
  });

  it("returns user, slug and resources when authenticated", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "ta" });
    getServerTenantSlug.mockResolvedValue("alpha");
    getServerCurrentUser.mockResolvedValue({ id: "u1", email: "a@b.c", role: "admin" });
    const ctx = await getTenantPageContext();
    expect(ctx.slug).toBe("alpha");
    expect(ctx.user.id).toBe("u1");
    expect(ctx.resources.billing).toBeDefined();
  });
});
