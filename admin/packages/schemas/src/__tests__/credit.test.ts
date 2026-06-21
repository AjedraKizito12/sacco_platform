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
  guarantorNominateSchema,
  loanApplicationRejectSchema,
  payrollBatchSchema,
  restructuringTypeSchema,
  type GuarantorOut,
  type LoanApplicationOut,
  type LoanProductOut,
  type LoanOut,
  type LoanInstallmentOut,
  type LoanRepaymentOut,
  type LoanStatementOut,
  type PayrollBatchOut,
  type RestructuringOut,
  type WriteOffOut,
  type LoanRecoveryOut,
} from "../credit";

describe("loanApplicationSchema", () => {
  const ok = {
    loan_product_id: "550e8400-e29b-41d4-a716-446655440000",
    member_id: "550e8400-e29b-41d4-a716-446655440001",
    requested_amount: "1000000.00",
    requested_term_periods: "12",
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

  it("rejects a non-numeric term", () => {
    expect(() =>
      loanApplicationSchema.parse({ ...ok, requested_term_periods: "12.5" }),
    ).toThrow();
  });

  it("rejects a zero term", () => {
    expect(() =>
      loanApplicationSchema.parse({ ...ok, requested_term_periods: "0" }),
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


describe("application + guarantor schemas (3d-2)", () => {
  const base = {
    loan_product_id: "550e8400-e29b-41d4-a716-446655440000",
    member_id: "550e8400-e29b-41d4-a716-446655440001",
    requested_amount: "1000000.00",
    purpose: "Working capital for the family shop",
    disbursement_destination: "member_savings",
    disbursement_account_id: "550e8400-e29b-41d4-a716-446655440002",
    idempotency_key: "1234567890ab",
  };

  it("accepts an integer-string term and rejects a non-numeric one", () => {
    expect(
      loanApplicationSchema.safeParse({ ...base, requested_term_periods: "12" }).success,
    ).toBe(true);
    expect(
      loanApplicationSchema.safeParse({ ...base, requested_term_periods: "x" }).success,
    ).toBe(false);
  });

  it("guarantorNominateSchema requires at least one member", () => {
    expect(guarantorNominateSchema.safeParse({ guarantor_member_ids: [] }).success).toBe(false);
    expect(
      guarantorNominateSchema.safeParse({
        guarantor_member_ids: ["550e8400-e29b-41d4-a716-446655440009"],
      }).success,
    ).toBe(true);
  });

  it("loanApplicationRejectSchema requires a reason", () => {
    expect(loanApplicationRejectSchema.safeParse({ reason: "" }).success).toBe(false);
    expect(
      loanApplicationRejectSchema.safeParse({ reason: "Insufficient collateral" }).success,
    ).toBe(true);
  });

  it("read types are structurally usable", () => {
    const a: LoanApplicationOut = {
      id: "a1",
      loan_product_id: "p1",
      member_id: "m1",
      requested_amount: "1000000.0000",
      requested_term_periods: 12,
      approved_amount: null,
      approved_term_periods: null,
      reviewed_by: null,
      reviewed_at: null,
      purpose: "x",
      disbursement_destination: "member_savings",
      disbursement_account_id: null,
      status: "pending",
      rejection_reason: null,
      decided_by: null,
      decided_at: null,
      approval_request_id: "r1",
      idempotency_key: "k",
      created_at: "t",
      updated_at: "t",
    };
    const g: GuarantorOut = {
      id: "g1",
      loan_application_id: "a1",
      guarantor_member_id: "m2",
      guaranteed_amount: "500000.0000",
      status: "pending",
      consented_at: null,
    };
    expect(a.status).toBe("pending");
    expect(g.status).toBe("pending");
  });
});


describe("loans servicing schemas (3d-3)", () => {
  const base = {
    loan_product_id: "550e8400-e29b-41d4-a716-446655440000",
    member_id: "550e8400-e29b-41d4-a716-446655440001",
    requested_amount: "1000000.00",
    requested_term_periods: "12",
    purpose: "Working capital for the family shop",
    disbursement_destination: "cash",
    idempotency_key: "1234567890ab",
  };

  it("requires disbursement_account_id on an application", () => {
    expect(loanApplicationSchema.safeParse(base).success).toBe(false);
    expect(
      loanApplicationSchema.safeParse({
        ...base,
        disbursement_account_id: "550e8400-e29b-41d4-a716-446655440002",
      }).success,
    ).toBe(true);
  });

  it("loan read types are structurally usable", () => {
    const loan: LoanOut = {
      id: "l1", loan_reference: "LN-202606-000001", loan_application_id: "a1",
      loan_product_id: "p1", member_id: "m1", status: "disbursed",
      principal_amount: "1000000.0000", outstanding_principal: "900000.0000",
      accrued_interest: "0.0000", accrued_penalties: "0.0000",
      annual_interest_rate: "18.5000", interest_method: "reducing_balance",
      repayment_frequency: "monthly", term_periods: 12,
      disbursement_destination: "cash", first_repayment_due: "2026-07-01",
      maturity_date: "2027-06-01", disbursed_at: "2026-06-21T00:00:00Z",
      created_at: "2026-06-21T00:00:00Z",
    };
    const inst: LoanInstallmentOut = {
      id: "i1", loan_id: "l1", period_number: 1, due_date: "2026-07-01",
      principal_due: "80000.0000", interest_due: "15000.0000", total_due: "95000.0000",
      principal_paid: "0.0000", interest_paid: "0.0000", status: "pending", paid_at: null,
    };
    const rep: LoanRepaymentOut = {
      id: "r1", loan_id: "l1", amount: "95000.0000", principal_applied: "80000.0000",
      interest_applied: "15000.0000", penalties_applied: "0.0000", overpayment: "0.0000",
      payment_account_id: "g1", journal_entry_id: "j1", posted_by: "u1",
      narration: null, idempotency_key: "k", created_at: "2026-06-21T00:00:00Z",
    };
    const st: LoanStatementOut = {
      loan_id: "l1", from_date: null, to_date: null,
      lines: [{ date: "2026-06-21", line_type: "disbursement", description: "Disbursed",
        debit: "1000000.0000", credit: "0.0000", running_balance: "1000000.0000" }],
    };
    expect(loan.term_periods).toBe(12);
    expect(inst.period_number).toBe(1);
    expect(rep.amount).toBe("95000.0000");
    expect(st.lines.length).toBe(1);
  });
});


describe("workout + payroll schemas (3d-4)", () => {
  it("restructuring type matches the backend (term_extension/payment_holiday)", () => {
    expect(restructuringTypeSchema.safeParse("payment_holiday").success).toBe(true);
    expect(restructuringTypeSchema.safeParse("term_extension").success).toBe(true);
    expect(restructuringTypeSchema.safeParse("principal_holiday").success).toBe(false);
  });
  it("loanRestructureSchema accepts an integer-string periods_added", () => {
    const ok = {
      restructuring_type: "term_extension",
      periods_added: "3",
      reason: "Borrower lost job, extending the term to ease repayment",
      idempotency_key: "1234567890ab",
    };
    expect(loanRestructureSchema.safeParse(ok).success).toBe(true);
    expect(loanRestructureSchema.safeParse({ ...ok, periods_added: "x" }).success).toBe(false);
  });
  it("payrollBatchSchema requires at least one row", () => {
    const row = { member_id: "550e8400-e29b-41d4-a716-446655440001", amount: "50000" };
    const cl = "550e8400-e29b-41d4-a716-446655440099";
    expect(
      payrollBatchSchema.safeParse({ rows: [], clearing_account_id: cl, idempotency_key: "1234567890ab" }).success,
    ).toBe(false);
    expect(
      payrollBatchSchema.safeParse({ rows: [row], clearing_account_id: cl, idempotency_key: "1234567890ab" }).success,
    ).toBe(true);
  });
  it("read types are structurally usable", () => {
    const w: WriteOffOut = { direct: true, approval_request_id: null, journal_entry_id: "j1" };
    const r: LoanRecoveryOut = { journal_entry_id: "j2" };
    const rs: RestructuringOut = {
      id: "rs1", loan_id: "l1", restructuring_type: "term_extension", periods_added: 3,
      new_term_periods: 15, new_maturity_date: "2027-09-01", reason: "x", executed_at: "2026-06-21T00:00:00Z",
    };
    const pb: PayrollBatchOut = {
      id: "b1", reference: "PB-202606-0001", status: "pending_review", total_rows: 2,
      matched_rows: 2, unmatched_rows: 0, total_amount: "100000.0000", source_format: "json",
      approval_request_id: null,
    };
    expect(w.direct).toBe(true);
    expect(r.journal_entry_id).toBe("j2");
    expect(rs.periods_added).toBe(3);
    expect(pb.status).toBe("pending_review");
  });
});
