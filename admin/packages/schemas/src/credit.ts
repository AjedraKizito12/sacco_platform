// admin/packages/schemas/src/credit.ts
import { z } from "zod";
import { idempotencyKey, intString, moneyString, percentageString, uuid } from "./common";

export const disbursementDestinationSchema = z.enum([
  "member_savings",
  "cash",
  "internal_gl",
]);

export const loanApplicationSchema = z.object({
  loan_product_id: uuid,
  member_id: uuid,
  requested_amount: moneyString({ min: "0.01" }),
  requested_term_periods: intString({ min: 1 }),
  purpose: z.string().trim().min(10, "Purpose required").max(500),
  disbursement_destination: disbursementDestinationSchema,
  disbursement_account_id: uuid,
  idempotency_key: idempotencyKey,
});

export const guarantorNominateSchema = z.object({
  guarantor_member_ids: z.array(uuid).min(1, "Select at least one guarantor"),
});

export const loanApplicationRejectSchema = z.object({
  reason: z.string().trim().min(1, "A reason is required").max(1000),
});

export const loanRepaymentSchema = z.object({
  amount: moneyString({ min: "0.01" }),
  payment_account_id: uuid,
  narration: z.string().trim().max(280).optional().or(z.literal("")),
  savings_account_id: uuid.optional(),
  idempotency_key: idempotencyKey,
});

export const disburseSchema = z.object({
  idempotency_key: idempotencyKey,
});

export const restructuringTypeSchema = z.enum([
  "term_extension",
  "payment_holiday",
]);

export const loanRestructureSchema = z.object({
  restructuring_type: restructuringTypeSchema,
  periods_added: intString({ min: 1 }),
  reason: z.string().trim().min(20, "Reason must be at least 20 chars").max(1000),
  idempotency_key: idempotencyKey,
});

export const payrollRowSchema = z.object({
  member_id: uuid,
  amount: moneyString({ min: "0.01" }),
});

export const payrollBatchSchema = z.object({
  rows: z.array(payrollRowSchema).min(1, "Add at least one row"),
  clearing_account_id: uuid,
  idempotency_key: idempotencyKey,
});

export const loanWriteOffSchema = z.object({
  amount: moneyString({ min: "0.01" }),
  reason: z.string().trim().min(20).max(1000),
  loan_loss_account_code: z
    .string()
    .trim()
    .max(20)
    .optional()
    .or(z.literal("")),
  idempotency_key: idempotencyKey,
});

export const loanRecoverySchema = z.object({
  amount: moneyString({ min: "0.01" }),
  reason: z.string().trim().min(10).max(500),
  idempotency_key: idempotencyKey,
});

export const loanProductSchema = z.object({
  name: z.string().trim().min(1).max(200),
  description: z.string().trim().max(1000).optional().or(z.literal("")),
  interest_method: z.enum(["flat", "reducing_balance"]),
  annual_interest_rate: percentageString({ max: 100 }),
  repayment_frequency: z.enum([
    "weekly",
    "biweekly",
    "monthly",
    "quarterly",
    "lump_sum",
  ]),
  max_term_periods: intString({ min: 1 }),
  min_amount: moneyString({ min: "0.01" }),
  max_amount: moneyString({ min: "0.01" }),
  required_approvals: intString({ min: 1 }),
  repayment_allocation: z.enum(["INTEREST_PRINCIPAL"]),
  disbursement_destinations: z.array(disbursementDestinationSchema).min(1),
  // GL account codes (strings) from the ledger; write_off_threshold is money.
  gl_principal_receivable_code: z.string().trim().min(1).max(20),
  gl_interest_receivable_code: z.string().trim().min(1).max(20),
  gl_interest_income_code: z.string().trim().min(1).max(20),
  gl_loan_loss_expense_code: z.string().trim().max(20).optional().or(z.literal("")),
  penalty_fee_type_code: z.string().trim().max(40).optional().or(z.literal("")),
  write_off_threshold: moneyString({ min: "0" }).optional().or(z.literal("")),
});

export const loanProductPatchSchema = z.object({
  name: z.string().trim().min(1).max(200).optional(),
  description: z.string().trim().max(1000).optional().or(z.literal("")),
  penalty_fee_type_code: z.string().trim().max(40).optional().or(z.literal("")),
  write_off_threshold: moneyString({ min: "0" }).optional().or(z.literal("")),
});

export type LoanApplicationInput = z.infer<typeof loanApplicationSchema>;
export type LoanRepaymentInput = z.infer<typeof loanRepaymentSchema>;
export type DisburseInput = z.infer<typeof disburseSchema>;
export type LoanRestructureInput = z.infer<typeof loanRestructureSchema>;
export type LoanWriteOffInput = z.infer<typeof loanWriteOffSchema>;
export type LoanRecoveryInput = z.infer<typeof loanRecoverySchema>;
export type LoanProductInput = z.infer<typeof loanProductSchema>;
export type LoanProductPatchInput = z.infer<typeof loanProductPatchSchema>;
export type GuarantorNominateInput = z.infer<typeof guarantorNominateSchema>;
export type LoanApplicationRejectInput = z.infer<typeof loanApplicationRejectSchema>;

// Mirror app/modules/credit/schemas.py. Decimals/uuids/datetimes are JSON strings.
export interface LoanApplicationOut {
  id: string;
  loan_product_id: string;
  member_id: string;
  requested_amount: string;
  requested_term_periods: number;
  approved_amount: string | null;
  approved_term_periods: number | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  purpose: string | null;
  disbursement_destination: string;
  disbursement_account_id: string | null;
  status: string;
  rejection_reason: string | null;
  decided_by: string | null;
  decided_at: string | null;
  approval_request_id: string | null;
  idempotency_key: string;
  created_at: string;
  updated_at: string;
}

export interface GuarantorOut {
  id: string;
  loan_application_id: string;
  guarantor_member_id: string;
  guaranteed_amount: string;
  status: string;
  consented_at: string | null;
}

export interface LoanOut {
  id: string;
  loan_reference: string;
  loan_application_id: string;
  loan_product_id: string;
  member_id: string;
  status: string;
  principal_amount: string;
  outstanding_principal: string;
  accrued_interest: string;
  accrued_penalties: string;
  annual_interest_rate: string;
  interest_method: string;
  repayment_frequency: string;
  term_periods: number;
  disbursement_destination: string;
  first_repayment_due: string | null;
  maturity_date: string | null;
  disbursed_at: string | null;
  created_at: string;
}

export interface LoanInstallmentOut {
  id: string;
  loan_id: string;
  period_number: number;
  due_date: string;
  principal_due: string;
  interest_due: string;
  total_due: string;
  principal_paid: string;
  interest_paid: string;
  status: string;
  paid_at: string | null;
}

export interface LoanRepaymentOut {
  id: string;
  loan_id: string;
  amount: string;
  principal_applied: string;
  interest_applied: string;
  penalties_applied: string;
  overpayment: string;
  payment_account_id: string;
  journal_entry_id: string;
  posted_by: string;
  narration: string | null;
  idempotency_key: string;
  created_at: string;
}

export interface StatementLineOut {
  date: string;
  line_type: string;
  description: string;
  debit: string;
  credit: string;
  running_balance: string;
}

export interface LoanStatementOut {
  loan_id: string;
  from_date: string | null;
  to_date: string | null;
  lines: StatementLineOut[];
}

export type PayrollRowInput = z.infer<typeof payrollRowSchema>;
export type PayrollBatchInput = z.infer<typeof payrollBatchSchema>;

export interface WriteOffOut {
  direct: boolean;
  approval_request_id: string | null;
  journal_entry_id: string | null;
}

export interface LoanRecoveryOut {
  journal_entry_id: string;
}

export interface RestructuringOut {
  id: string;
  loan_id: string;
  restructuring_type: string;
  periods_added: number;
  new_term_periods: number;
  new_maturity_date: string;
  reason: string;
  executed_at: string;
}

export interface PayrollBatchOut {
  id: string;
  reference: string;
  status: string;
  total_rows: number;
  matched_rows: number;
  unmatched_rows: number;
  total_amount: string;
  source_format: string;
  approval_request_id: string | null;
}

// Mirror app/modules/credit/schemas.py::LoanProductOut. Decimals are JSON strings.
export interface LoanProductOut {
  id: string;
  name: string;
  description: string | null;
  interest_method: string;
  annual_interest_rate: string;
  repayment_frequency: string;
  max_term_periods: number;
  min_amount: string;
  max_amount: string;
  required_approvals: number;
  disbursement_destinations: string[];
  repayment_allocation: string;
  gl_principal_receivable_code: string;
  gl_interest_receivable_code: string;
  gl_interest_income_code: string;
  gl_loan_loss_expense_code: string | null;
  penalty_fee_type_code: string | null;
  write_off_threshold: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
