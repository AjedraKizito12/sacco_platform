import { describe, expect, it } from "vitest";
import {
  createTenantSchema,
  impersonationRequestSchema,
  suggestSlug,
  tenantPatchSchema,
  tenantSuspendSchema,
} from "../tenants";

describe("createTenantSchema", () => {
  it("accepts a valid payload", () => {
    const res = createTenantSchema.safeParse({
      slug: "kampala-teachers",
      name: "Kampala Teachers SACCO",
      admin_email: "admin@example.com",
    });
    expect(res.success).toBe(true);
  });

  it("accepts an empty admin_email (optional seed user)", () => {
    const res = createTenantSchema.safeParse({ slug: "k1", name: "K1", admin_email: "" });
    expect(res.success).toBe(true);
  });

  it("rejects an uppercase slug", () => {
    const res = createTenantSchema.safeParse({ slug: "Kampala", name: "X", admin_email: "" });
    expect(res.success).toBe(false);
  });

  it("rejects a slug over 40 chars", () => {
    const res = createTenantSchema.safeParse({ slug: "a".repeat(41), name: "X", admin_email: "" });
    expect(res.success).toBe(false);
  });

  it("rejects a junk admin_email", () => {
    const res = createTenantSchema.safeParse({ slug: "ok", name: "X", admin_email: "not-an-email" });
    expect(res.success).toBe(false);
  });

  it("trims and lowercases admin_email", () => {
    const parsed = createTenantSchema.parse({ slug: "ok", name: "X", admin_email: " ADMIN@Example.com " });
    expect(parsed.admin_email).toBe("admin@example.com");
  });

  it("rejects a whitespace-only name", () => {
    const res = createTenantSchema.safeParse({ slug: "ok", name: "   ", admin_email: "" });
    expect(res.success).toBe(false);
  });

  it("accepts a slug at exactly 40 chars", () => {
    const res = createTenantSchema.safeParse({ slug: "a".repeat(40), name: "X", admin_email: "" });
    expect(res.success).toBe(true);
  });
});

describe("suggestSlug", () => {
  it("lowercases and hyphenates words", () => {
    expect(suggestSlug("Kampala Teachers SACCO")).toBe("kampala-teachers-sacco");
  });
  it("collapses punctuation runs into single hyphens", () => {
    expect(suggestSlug("St. Mary's -- Co-op!")).toBe("st-mary-s-co-op");
  });
  it("strips leading/trailing hyphens and caps at 40 chars", () => {
    const out = suggestSlug("  --" + "very long sacco name ".repeat(4) + "--  ");
    expect(out.length).toBeLessThanOrEqual(40);
    expect(out.startsWith("-")).toBe(false);
    expect(out.endsWith("-")).toBe(false);
  });
  it("returns empty string for names with no usable characters", () => {
    expect(suggestSlug("!!!")).toBe("");
  });
  it("strips a trailing hyphen introduced by the 40-char cut", () => {
    expect(suggestSlug("x".repeat(39) + " extra")).toBe("x".repeat(39));
  });
});

describe("tenantPatchSchema", () => {
  it("accepts a non-empty name", () => {
    expect(tenantPatchSchema.safeParse({ name: "Renamed SACCO" }).success).toBe(true);
  });
  it("rejects a whitespace-only name", () => {
    expect(tenantPatchSchema.safeParse({ name: "   " }).success).toBe(false);
  });
  it("rejects a name over 200 chars", () => {
    expect(tenantPatchSchema.safeParse({ name: "a".repeat(201) }).success).toBe(false);
  });
});

describe("tenantSuspendSchema", () => {
  it("accepts a reason of at least 10 chars", () => {
    expect(tenantSuspendSchema.safeParse({ reason: "Non-payment for 90 days" }).success).toBe(true);
  });
  it("rejects a reason under 10 chars", () => {
    expect(tenantSuspendSchema.safeParse({ reason: "too short" }).success).toBe(false);
  });
  it("rejects a reason over 500 chars", () => {
    expect(tenantSuspendSchema.safeParse({ reason: "a".repeat(501) }).success).toBe(false);
  });
});

describe("impersonationRequestSchema", () => {
  it("accepts a reason of at least 10 chars", () => {
    expect(impersonationRequestSchema.safeParse({ reason: "Investigating a posting bug" }).success).toBe(true);
  });
  it("rejects a reason under 10 chars", () => {
    expect(impersonationRequestSchema.safeParse({ reason: "debug" }).success).toBe(false);
  });
});
