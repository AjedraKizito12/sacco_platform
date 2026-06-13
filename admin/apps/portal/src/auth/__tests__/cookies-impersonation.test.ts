import { describe, expect, it, vi } from "vitest";

const store = new Map<string, string>();
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({
    set: (name: string, value: string) => store.set(name, value),
    get: (name: string) => (store.has(name) ? { value: store.get(name) } : undefined),
    delete: (name: string) => store.delete(name),
  })),
}));

import {
  IMPERSONATION_COOKIE,
  clearImpersonationCookie,
  readImpersonationCookie,
  setImpersonationCookie,
} from "../cookies";

describe("impersonation cookie helpers", () => {
  it("round-trips the impersonation marker", async () => {
    await setImpersonationCookie({
      id: "imp1",
      tenantName: "Alpha SACCO",
      expiresAt: "2026-06-13T12:30:00Z",
      tenantId: "t1",
    });
    const read = await readImpersonationCookie();
    expect(read).toEqual({
      id: "imp1",
      tenantName: "Alpha SACCO",
      expiresAt: "2026-06-13T12:30:00Z",
      tenantId: "t1",
    });
    expect(store.get(IMPERSONATION_COOKIE)).toBeTruthy();
  });

  it("returns null when absent", async () => {
    store.delete(IMPERSONATION_COOKIE);
    expect(await readImpersonationCookie()).toBeNull();
  });

  it("returns null on malformed JSON", async () => {
    store.set(IMPERSONATION_COOKIE, "not-json");
    expect(await readImpersonationCookie()).toBeNull();
  });

  it("clears the cookie", async () => {
    await setImpersonationCookie({ id: "imp1", tenantName: "A", expiresAt: "x", tenantId: "t1" });
    await clearImpersonationCookie();
    expect(store.has(IMPERSONATION_COOKIE)).toBe(false);
  });
});
