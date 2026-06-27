import { describe, it, expect, vi, beforeEach } from "vitest";

const { redirect, getServerAccessToken, getServerCurrentUser, getServerTenantSlug } =
  vi.hoisted(() => ({
    redirect: vi.fn((u: string) => {
      throw new Error(`REDIRECT:${u}`);
    }),
    getServerAccessToken: vi.fn(),
    getServerCurrentUser: vi.fn(),
    getServerTenantSlug: vi.fn(),
  }));
vi.mock("next/navigation", () => ({ redirect }));
vi.mock("@/auth/server-helpers", () => ({
  getServerAccessToken: (...a: unknown[]) => getServerAccessToken(...a),
  getServerCurrentUser: (...a: unknown[]) => getServerCurrentUser(...a),
  getServerTenantSlug: (...a: unknown[]) => getServerTenantSlug(...a),
}));

import MemberAuthedLayout from "../layout";

beforeEach(() => {
  redirect.mockClear();
  getServerAccessToken.mockReset();
  getServerCurrentUser.mockReset();
  getServerTenantSlug.mockReset();
  getServerTenantSlug.mockResolvedValue("acme");
});

describe("MemberAuthedLayout", () => {
  it("redirects to /member/login with no token", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: null });
    await expect(MemberAuthedLayout({ children: null })).rejects.toThrow(
      "REDIRECT:/member/login",
    );
  });

  it("redirects to /member/login with no slug", async () => {
    getServerTenantSlug.mockResolvedValue(null);
    getServerAccessToken.mockResolvedValue({ accessToken: "tok" });
    await expect(MemberAuthedLayout({ children: null })).rejects.toThrow(
      "REDIRECT:/member/login",
    );
  });
});
