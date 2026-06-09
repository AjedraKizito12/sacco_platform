// admin/packages/schemas/src/__tests__/credit.test.ts
import { describe, expect, it } from "vitest";
import {
  loanApplicationSchema,
  loanRepaymentSchema,
  loanRestructureSchema,
  loanWriteOffSchema,
} from "../credit";

describe("loanApplicationSchema", () => {
  const ok = {
    loan_product_id: "550e8400-e29b-41d4-a716-446655440000",
    member_id: "550e8400-e29b-41d4-a716-446655440001",
    requested_amount: "1000000.00",
    requested_term_periods: 12,
    purpose: "Working capital for the family shop",
    disbursement_destination: "savings_account",
    disbursement_account_id: "550e8400-e29b-41d4-a716-446655440002",
    idempotency_key: "1234567890ab",
  };

  it("accepts a complete application", () => {
    expect(() => loanApplicationSchema.parse(ok)).not.toThrow();
  });

  it("rejects too-short purpose", () => {
    expect(() =>
      loanApplicationSchema.parse({ ...ok, purpose: "biz" }),
    ).toThrow();
  });

  it("rejects fractional term periods", () => {
    expect(() =>
      loanApplicationSchema.parse({ ...ok, requested_term_periods: 12.5 }),
    ).toThrow();
  });

  it("rejects out-of-range term", () => {
    expect(() =>
      loanApplicationSchema.parse({ ...ok, requested_term_periods: 0 }),
    ).toThrow();
    expect(() =>
      loanApplicationSchema.parse({ ...ok, requested_term_periods: 400 }),
    ).toThrow();
  });
});

describe("loanRepaymentSchema", () => {
  it("accepts savings_account_id as optional", () => {
    expect(() =>
      loanRepaymentSchema.parse({
        amount: "100000",
        payment_account_id: "550e8400-e29b-41d4-a716-446655440000",
        idempotency_key: "1234567890ab",
      }),
    ).not.toThrow();
  });
});

describe("loanRestructureSchema", () => {
  it("requires periods_added ≥ 1", () => {
    expect(() =>
      loanRestructureSchema.parse({
        restructuring_type: "term_extension",
        periods_added: 0,
        reason: "Borrower lost job, requesting term extension to recover",
        idempotency_key: "1234567890ab",
      }),
    ).toThrow();
  });
});

describe("loanWriteOffSchema", () => {
  it("rejects empty reason", () => {
    expect(() =>
      loanWriteOffSchema.parse({
        amount: "500000",
        reason: "too short",
        idempotency_key: "1234567890ab",
      }),
    ).toThrow();
  });
});
