// admin/packages/schemas/src/__tests__/credit.test.ts
import { describe, expect, it } from "vitest";
import {
  loanApplicationSchema,
  loanProductPatchSchema,
  loanProductSchema,
  loanRepaymentSchema,
  loanRestructureSchema,
  loanWriteOffSchema,
  disbursementDestinationSchema,
  type LoanProductOut,
} from "../credit";

describe("loanApplicationSchema", () => {
  const ok = {
    loan_product_id: "550e8400-e29b-41d4-a716-446655440000",
    member_id: "550e8400-e29b-41d4-a716-446655440001",
    requested_amount: "1000000.00",
    requested_term_periods: 12,
    purpose: "Working capital for the family shop",
    disbursement_destination: "member_savings",
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


const validProduct = {
  name: "Personal Loan",
  description: "",
  interest_method: "reducing_balance",
  annual_interest_rate: "18.5",
  repayment_frequency: "monthly",
  max_term_periods: "24",
  min_amount: "100000",
  max_amount: "5000000",
  required_approvals: "1",
  repayment_allocation: "INTEREST_PRINCIPAL",
  disbursement_destinations: ["member_savings"],
  gl_principal_receivable_code: "1200",
  gl_interest_receivable_code: "1210",
  gl_interest_income_code: "4100",
  gl_loan_loss_expense_code: "5100",
  penalty_fee_type_code: "",
  write_off_threshold: "0",
};

describe("loanProductSchema (corrected to backend enums)", () => {
  it("accepts the backend's real enum values", () => {
    expect(loanProductSchema.safeParse(validProduct).success).toBe(true);
  });
  it("rejects stale destination values, accepts new ones", () => {
    expect(disbursementDestinationSchema.safeParse("savings_account").success).toBe(false);
    expect(disbursementDestinationSchema.safeParse("member_savings").success).toBe(true);
  });
  it("rejects a stale repayment_frequency, accepts lump_sum", () => {
    expect(
      loanProductSchema.safeParse({ ...validProduct, repayment_frequency: "annual" }).success,
    ).toBe(false);
    expect(
      loanProductSchema.safeParse({ ...validProduct, repayment_frequency: "lump_sum" }).success,
    ).toBe(true);
  });
  it("rejects a blank name and an empty destinations list", () => {
    expect(loanProductSchema.safeParse({ ...validProduct, name: "" }).success).toBe(false);
    expect(
      loanProductSchema.safeParse({ ...validProduct, disbursement_destinations: [] }).success,
    ).toBe(false);
  });
});

describe("loanProductPatchSchema", () => {
  it("accepts a partial payload and an empty payload", () => {
    expect(loanProductPatchSchema.safeParse({ name: "Renamed" }).success).toBe(true);
    expect(loanProductPatchSchema.safeParse({}).success).toBe(true);
  });
});

describe("LoanProductOut", () => {
  it("is structurally usable", () => {
    const p: LoanProductOut = {
      id: "p1",
      name: "Personal Loan",
      description: null,
      interest_method: "reducing_balance",
      annual_interest_rate: "18.5000",
      repayment_frequency: "monthly",
      max_term_periods: 24,
      min_amount: "100000.0000",
      max_amount: "5000000.0000",
      required_approvals: 1,
      disbursement_destinations: ["member_savings"],
      repayment_allocation: "INTEREST_PRINCIPAL",
      gl_principal_receivable_code: "1200",
      gl_interest_receivable_code: "1210",
      gl_interest_income_code: "4100",
      gl_loan_loss_expense_code: "5100",
      penalty_fee_type_code: null,
      write_off_threshold: "0.0000",
      is_active: true,
      created_at: "2026-06-21T00:00:00Z",
      updated_at: "2026-06-21T00:00:00Z",
    };
    expect(p.max_term_periods).toBe(24);
  });
});
