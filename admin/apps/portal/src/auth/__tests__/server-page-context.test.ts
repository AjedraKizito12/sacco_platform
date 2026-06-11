import { describe, expect, it, vi, beforeEach } from "vitest";

// vi.mock calls are hoisted to top-of-file; factories cannot reference
// regular const/let declarations (TDZ). Use vi.hoisted() so the mock
// variable is available when the hoisted factory executes.
const { redirectMock, getServerAccessToken, getServerCurrentUser } = vi.hoisted(
  () => ({
    redirectMock: vi.fn((url: string) => {
      throw new Error(`REDIRECT:${url}`);
    }),
    getServerAccessToken: vi.fn(),
    getServerCurrentUser: vi.fn(),
  }),
);

vi.mock("next/navigation", () => ({ redirect: redirectMock }));

vi.mock("../server-helpers", () => ({
  getServerAccessToken: (...a: unknown[]) => getServerAccessToken(...a),
  getServerCurrentUser: (...a: unknown[]) => getServerCurrentUser(...a),
}));

import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "../server-page-context";

beforeEach(() => {
  redirectMock.mockClear();
  getServerAccessToken.mockReset();
  getServerCurrentUser.mockReset();
});

describe("getPlatformPageContext", () => {
  it("redirects to login when there is no access token", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: null });
    await expect(getPlatformPageContext()).rejects.toThrow(
      "REDIRECT:/platform/login",
    );
  });

  it("redirects to login when the current user cannot be fetched", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "tok" });
    getServerCurrentUser.mockResolvedValue(null);
    await expect(getPlatformPageContext()).rejects.toThrow(
      "REDIRECT:/platform/login",
    );
  });

  it("returns user + resources when authenticated", async () => {
    getServerAccessToken.mockResolvedValue({ accessToken: "tok" });
    getServerCurrentUser.mockResolvedValue({
      id: "u1",
      email: "a@b.c",
      full_name: "A",
      is_active: true,
      is_superuser: true,
      role: "superuser",
    });
    const ctx = await getPlatformPageContext();
    expect(ctx.user.id).toBe("u1");
    expect(typeof ctx.resources.admin.listUsers).toBe("function");
  });
});

describe("requirePlatformPermission", () => {
  it("redirects to /permission-denied when the user lacks the permission", () => {
    const supportUser = {
      id: "u2", email: "s@b.c", full_name: "S",
      is_active: true, is_superuser: false, role: "support" as const,
    };
    expect(() =>
      requirePlatformPermission(supportUser, "platform.users.write"),
    ).toThrow("REDIRECT:/permission-denied");
  });

  it("does not redirect when the user has the permission", () => {
    const adminUser = {
      id: "u3", email: "ad@b.c", full_name: "Ad",
      is_active: true, is_superuser: false, role: "admin" as const,
    };
    expect(() =>
      requirePlatformPermission(adminUser, "platform.users.read"),
    ).not.toThrow();
  });
});
