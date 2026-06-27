import { describe, it, expect, vi, beforeEach } from "vitest";

// vi.mock calls are hoisted to top-of-file; factories cannot reference
// regular const/let declarations (TDZ). Use vi.hoisted() so the mock
// variables are available when the hoisted factory executes.
const {
  redirectMock,
  getServerAccessToken,
  getServerCurrentUser,
  getServerTenantSlug,
} = vi.hoisted(() => ({
  redirectMock: vi.fn((url: string) => {
    throw new Error(`REDIRECT:${url}`);
  }),
  getServerAccessToken: vi.fn(),
  getServerCurrentUser: vi.fn(),
  getServerTenantSlug: vi.fn(),
}));

vi.mock("next/navigation", () => ({ redirect: redirectMock }));

vi.mock("../server-helpers", () => ({
  getServerAccessToken: (...a: unknown[]) => getServerAccessToken(...a),
  getServerCurrentUser: (...a: unknown[]) => getServerCurrentUser(...a),
  getServerTenantSlug: (...a: unknown[]) => getServerTenantSlug(...a),
}));

import { getMemberPageContext } from "../server-page-context";

beforeEach(() => {
  redirectMock.mockClear();
  getServerAccessToken.mockReset();
  getServerCurrentUser.mockReset();
  getServerTenantSlug.mockReset();
});

describe("getMemberPageContext", () => {
  it("redirects to /member/login when no access token", async () => {
    getServerTenantSlug.mockResolvedValue("acme");
    getServerAccessToken.mockResolvedValue({ accessToken: null });
    await expect(getMemberPageContext()).rejects.toThrow(
      "REDIRECT:/member/login",
    );
  });

  it("returns member + slug + resources when authenticated", async () => {
    getServerTenantSlug.mockResolvedValue("acme");
    getServerAccessToken.mockResolvedValue({ accessToken: "tok" });
    getServerCurrentUser.mockResolvedValue({ id: "m1", full_name: "Jane" });
    const ctx = await getMemberPageContext();
    expect(ctx.slug).toBe("acme");
    expect(ctx.member).toMatchObject({ id: "m1" });
    expect(ctx.resources).toBeTruthy();
  });
});
