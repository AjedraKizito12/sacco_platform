import { describe, expect, it } from "vitest";
import {
  tenantUserCreateSchema,
  tenantUserPatchSchema,
  tenantUserRoleLabel,
} from "../tenant-users";

describe("tenant-user schemas", () => {
  it("create requires a valid email and non-empty name", () => {
    expect(tenantUserCreateSchema.safeParse({ email: "x", full_name: "A" }).success).toBe(false);
    expect(
      tenantUserCreateSchema.safeParse({ email: "a@b.co", full_name: "Ada", is_admin: true })
        .success,
    ).toBe(true);
  });
  it("patch accepts a partial body", () => {
    expect(tenantUserPatchSchema.safeParse({ is_active: false }).success).toBe(true);
  });
  it("role label maps is_admin", () => {
    expect(tenantUserRoleLabel(true)).toBe("Admin");
    expect(tenantUserRoleLabel(false)).toBe("Member");
  });
});
