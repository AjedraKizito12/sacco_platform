// admin/packages/schemas/src/__tests__/member.test.ts
import { describe, expect, it } from "vitest";
import {
  memberRegistrationSchema,
  memberStatusChangeSchema,
} from "../member";

describe("memberRegistrationSchema", () => {
  it("accepts a minimal valid member", () => {
    expect(() =>
      memberRegistrationSchema.parse({
        full_name: "Mary Akello",
        date_of_birth: "1990-05-12",
        gender: "F",
      }),
    ).not.toThrow();
  });

  it("rejects an invalid gender", () => {
    expect(() =>
      memberRegistrationSchema.parse({
        full_name: "Mary",
        date_of_birth: "1990-05-12",
        gender: "?",
      }),
    ).toThrow();
  });

  it("accepts an empty optional email", () => {
    expect(() =>
      memberRegistrationSchema.parse({
        full_name: "Mary",
        date_of_birth: "1990-05-12",
        gender: "F",
        email: "",
      }),
    ).not.toThrow();
  });

  it("rejects malformed phone", () => {
    expect(() =>
      memberRegistrationSchema.parse({
        full_name: "Mary",
        date_of_birth: "1990-05-12",
        gender: "F",
        phone: "phone???",
      }),
    ).toThrow();
  });
});

describe("memberStatusChangeSchema", () => {
  it("requires a reason ≥ 10 chars", () => {
    expect(() =>
      memberStatusChangeSchema.parse({
        new_status: "dormant",
        reason: "short",
        idempotency_key: "12345678",
      }),
    ).toThrow(/at least 10/);
  });

  it("accepts a valid status change", () => {
    expect(() =>
      memberStatusChangeSchema.parse({
        new_status: "suspended",
        reason: "Member missed three consecutive savings deposits",
        idempotency_key: "12345678",
      }),
    ).not.toThrow();
  });
});
