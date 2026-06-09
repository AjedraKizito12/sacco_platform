import { describe, expect, it } from "vitest";
import { resolveTenantSlug } from "@/auth/tenant-resolver";

describe("resolveTenantSlug", () => {
  it("extracts subdomain in production", () => {
    expect(
      resolveTenantSlug({
        host: "sacco-one.app.sacco.example",
        searchParams: new URLSearchParams(),
        cookieValue: null,
        rootDomain: "app.sacco.example",
      }),
    ).toBe("sacco-one");
  });

  it("returns null for the root domain", () => {
    expect(
      resolveTenantSlug({
        host: "app.sacco.example",
        searchParams: new URLSearchParams(),
        cookieValue: null,
        rootDomain: "app.sacco.example",
      }),
    ).toBeNull();
  });

  it("falls back to query param in dev", () => {
    expect(
      resolveTenantSlug({
        host: "localhost:3000",
        searchParams: new URLSearchParams("tenant=sacco-two"),
        cookieValue: null,
      }),
    ).toBe("sacco-two");
  });

  it("falls back to cookie", () => {
    expect(
      resolveTenantSlug({
        host: "localhost:3000",
        searchParams: new URLSearchParams(),
        cookieValue: "sacco-three",
      }),
    ).toBe("sacco-three");
  });

  it("rejects malformed slugs", () => {
    expect(
      resolveTenantSlug({
        host: "localhost:3000",
        searchParams: new URLSearchParams("tenant=Bad..Slug"),
        cookieValue: null,
      }),
    ).toBeNull();
  });
});
