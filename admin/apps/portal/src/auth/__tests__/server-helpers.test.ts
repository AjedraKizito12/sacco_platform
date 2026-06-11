import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Mutable per-test fixtures for the mocked Next.js request stores.
let cookieValues: Record<string, string>;
let headerValues: Record<string, string>;

vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({
    get: (name: string) =>
      name in cookieValues ? { value: cookieValues[name] as string } : undefined,
  })),
  headers: vi.fn(async () => ({
    get: (name: string) => headerValues[name] ?? null,
  })),
}));

const fetchMock = vi.fn();

beforeEach(() => {
  // Fresh module instance per test so the cache()-wrapped helpers start with
  // an empty request-scoped memo and never leak state across tests.
  vi.resetModules();
  cookieValues = {};
  headerValues = {};
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return { ok, status, json: async () => body } as unknown as Response;
}

function lastFetchInit(): { method?: string; headers: Record<string, string> } {
  const call = fetchMock.mock.calls.at(-1);
  if (!call) throw new Error("fetch was not called");
  return call[1] as { method?: string; headers: Record<string, string> };
}

describe("getServerAccessToken", () => {
  it("returns null without calling the backend when no refresh cookie is present", async () => {
    const { getServerAccessToken } = await import("../server-helpers");
    const result = await getServerAccessToken("platform");
    expect(result).toEqual({ accessToken: null, expiresIn: null });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("refreshes against the platform endpoint and returns the access token", async () => {
    cookieValues["sacco_refresh_platform"] = "refresh-abc";
    fetchMock.mockResolvedValue(
      jsonResponse({ access_token: "acc-1", expires_in: 900 }),
    );
    const { getServerAccessToken } = await import("../server-helpers");
    const result = await getServerAccessToken("platform");
    expect(result).toEqual({ accessToken: "acc-1", expiresIn: 900 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain("/platform/auth/refresh");
    expect(lastFetchInit().method).toBe("POST");
  });

  it("returns null when the refresh request is rejected by the backend", async () => {
    cookieValues["sacco_refresh_platform"] = "refresh-abc";
    fetchMock.mockResolvedValue(jsonResponse({}, false, 401));
    const { getServerAccessToken } = await import("../server-helpers");
    const result = await getServerAccessToken("platform");
    expect(result).toEqual({ accessToken: null, expiresIn: null });
  });

  it("requires a tenant slug for the tenant variant", async () => {
    cookieValues["sacco_refresh_tenant"] = "refresh-xyz";
    // No slug cookie/header set -> the tenant refresh short-circuits to null.
    const { getServerAccessToken } = await import("../server-helpers");
    const result = await getServerAccessToken("tenant");
    expect(result).toEqual({ accessToken: null, expiresIn: null });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("getServerCurrentUser", () => {
  it("returns the user shape and sends the bearer token to the platform /me endpoint", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        id: "u1",
        email: "a@b.c",
        full_name: "A",
        is_active: true,
        is_superuser: true,
        role: "superuser",
      }),
    );
    const { getServerCurrentUser } = await import("../server-helpers");
    const user = await getServerCurrentUser("platform", "acc-1");
    expect(user?.id).toBe("u1");
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url).toContain("/platform/auth/me");
    expect(lastFetchInit().headers["Authorization"]).toBe("Bearer acc-1");
  });

  it("returns null when /me responds non-ok", async () => {
    fetchMock.mockResolvedValue(jsonResponse({}, false, 401));
    const { getServerCurrentUser } = await import("../server-helpers");
    const user = await getServerCurrentUser("platform", "bad-token");
    expect(user).toBeNull();
  });
});
