// admin/packages/schemas/src/__tests__/member.test.ts
import { describe, expect, it } from "vitest";
import {
  memberRegistrationSchema,
  memberStatusChangeSchema,
  type MemberOut,
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

describe("MemberOut", () => {
  it("is structurally usable with nullable optional fields", () => {
    const m: MemberOut = {
      id: "m1",
      member_number: "M-0001",
      full_name: "Ada Loan",
      date_of_birth: "2000-01-01",
      gender: "F",
      phone: null,
      email: null,
      physical_address: null,
      national_id_number: null,
      id_document_type: null,
      id_document_number: null,
      id_issued_date: null,
      id_expiry_date: null,
      status: "active",
      joined_at: "2026-06-01",
      created_at: "2026-06-01T00:00:00Z",
      updated_at: "2026-06-01T00:00:00Z",
    };
    expect(m.member_number).toBe("M-0001");
  });
});

import { memberStatementRangeSchema } from "../member";

describe("memberStatementRangeSchema", () => {
  it("accepts blanks and a valid range", () => {
    expect(memberStatementRangeSchema.safeParse({ from_date: "", to_date: "" }).success).toBe(true);
    expect(
      memberStatementRangeSchema.safeParse({ from_date: "2026-01-01", to_date: "2026-02-01" }).success,
    ).toBe(true);
  });

  it("rejects from after to", () => {
    const r = memberStatementRangeSchema.safeParse({ from_date: "2026-03-01", to_date: "2026-01-01" });
    expect(r.success).toBe(false);
  });
});
