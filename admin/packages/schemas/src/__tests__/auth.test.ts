// admin/packages/schemas/src/__tests__/auth.test.ts
import { describe, expect, it } from "vitest";
import {
  loginSchema,
  passwordResetConfirmSchema,
  passwordResetRequestSchema,
} from "../auth";

describe("loginSchema", () => {
  it("normalises email to lowercase", () => {
    const parsed = loginSchema.parse({
      email: "  Liam@SACCO.example  ",
      password: "AdminTest!2026",
    });
    expect(parsed.email).toBe("liam@sacco.example");
  });

  it("rejects empty password", () => {
    expect(() =>
      loginSchema.parse({ email: "x@y.test", password: "" }),
    ).toThrow();
  });
});

describe("passwordResetRequestSchema", () => {
  it("accepts a valid email", () => {
    expect(() =>
      passwordResetRequestSchema.parse({ email: "x@y.test" }),
    ).not.toThrow();
  });
});

describe("passwordResetConfirmSchema", () => {
  it("requires min length 12 password", () => {
    expect(() =>
      passwordResetConfirmSchema.parse({
        token: "abcdefghij",
        new_password: "short",
        confirm_password: "short",
      }),
    ).toThrow(/at least 12/);
  });

  it("enforces password match", () => {
    expect(() =>
      passwordResetConfirmSchema.parse({
        token: "abcdefghij",
        new_password: "longenoughpw1!",
        confirm_password: "different-pw-here",
      }),
    ).toThrow(/do not match/);
  });

  it("accepts matching strong password", () => {
    expect(() =>
      passwordResetConfirmSchema.parse({
        token: "abcdefghij",
        new_password: "Abcdefghijkl12!",
        confirm_password: "Abcdefghijkl12!",
      }),
    ).not.toThrow();
  });
});
