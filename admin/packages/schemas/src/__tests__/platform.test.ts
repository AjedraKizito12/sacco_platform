// admin/packages/schemas/src/__tests__/platform.test.ts
import { describe, expect, it } from "vitest";
import {
  createPlatformUserSchema,
  platformRoleSchema,
  updatePlatformUserSchema,
} from "../platform";

describe("platformRoleSchema", () => {
  it("accepts the four roles", () => {
    for (const r of ["superuser", "admin", "finance", "support"]) {
      expect(platformRoleSchema.safeParse(r).success).toBe(true);
    }
  });
  it("rejects unknown roles", () => {
    expect(platformRoleSchema.safeParse("root").success).toBe(false);
  });
});

describe("createPlatformUserSchema", () => {
  it("accepts a valid payload and defaults role to support", () => {
    const parsed = createPlatformUserSchema.parse({
      email: "ops@example.com",
      full_name: "Ops Person",
    });
    expect(parsed.role).toBe("support");
  });
  it("rejects an invalid email", () => {
    const res = createPlatformUserSchema.safeParse({
      email: "not-an-email",
      full_name: "X",
    });
    expect(res.success).toBe(false);
  });
  it("rejects an empty full_name", () => {
    const res = createPlatformUserSchema.safeParse({
      email: "ops@example.com",
      full_name: "",
    });
    expect(res.success).toBe(false);
  });
  it("rejects a whitespace-only full_name", () => {
    const res = createPlatformUserSchema.safeParse({
      email: "ops@example.com",
      full_name: "   ",
    });
    expect(res.success).toBe(false);
  });
  it("trims and lowercases email on parse", () => {
    const parsed = createPlatformUserSchema.parse({
      email: " OPS@Example.com ",
      full_name: "X",
    });
    expect(parsed.email).toBe("ops@example.com");
  });
});

describe("updatePlatformUserSchema", () => {
  it("requires full_name, is_active, role together", () => {
    const res = updatePlatformUserSchema.safeParse({
      full_name: "Renamed",
      is_active: true,
      role: "admin",
    });
    expect(res.success).toBe(true);
  });
  it("rejects a missing role", () => {
    const res = updatePlatformUserSchema.safeParse({
      full_name: "Renamed",
      is_active: true,
    });
    expect(res.success).toBe(false);
  });
});
