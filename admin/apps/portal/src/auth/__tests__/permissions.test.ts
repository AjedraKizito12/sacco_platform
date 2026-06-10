import { describe, expect, it } from "vitest";
import {
  PermissionDeniedError,
  requirePermission,
  userHasPermission,
} from "../permissions";

const superuser = {
  id: "u1",
  email: "s@test.example",
  full_name: "S",
  is_active: true,
  is_superuser: true,
};

const admin = {
  id: "u2",
  email: "a@test.example",
  full_name: "A",
  is_active: true,
  is_superuser: false,
  role: "admin" as const,
};

const finance = {
  id: "u4",
  email: "f@test.example",
  full_name: "F",
  is_active: true,
  is_superuser: false,
  role: "finance" as const,
};

const support = {
  id: "u3",
  email: "t@test.example",
  full_name: "T",
  is_active: true,
  is_superuser: false,
  role: "support" as const,
};

describe("userHasPermission", () => {
  it("grants superuser everything", () => {
    expect(userHasPermission(superuser, "billing.write")).toBe(true);
    expect(userHasPermission(superuser, "platform.security.jwt_keys.read")).toBe(
      true,
    );
  });

  it("respects role-min mappings", () => {
    expect(userHasPermission(admin, "billing.write")).toBe(true);
    expect(userHasPermission(admin, "platform.security.jwt_keys.read")).toBe(
      false,
    );
    expect(userHasPermission(support, "platform.tenants.read")).toBe(true);
    expect(userHasPermission(support, "billing.write")).toBe(false);
    expect(userHasPermission(finance, "billing.read")).toBe(true);
    expect(userHasPermission(finance, "billing.write")).toBe(false);
  });

  it("denies unknown permissions by default", () => {
    expect(userHasPermission(admin, "fictional.permission")).toBe(false);
  });

  it("denies a null user", () => {
    expect(userHasPermission(null, "billing.read")).toBe(false);
  });
});

describe("requirePermission", () => {
  it("throws when user fails", () => {
    expect(() => requirePermission(support, "billing.write")).toThrow(
      PermissionDeniedError,
    );
  });
  it("passes when user has rank", () => {
    expect(() => requirePermission(admin, "billing.write")).not.toThrow();
  });
});
