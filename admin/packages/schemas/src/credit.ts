// admin/packages/schemas/src/credit.ts
import { z } from "zod";
import { idempotencyKey, moneyString, percentageString, uuid } from "./common";

export const disbursementDestinationSchema = z.enum([
  "savings_account",
  "cash",
  "bank_transfer",
  "mobile_money",
]);

export const loanApplicationSchema = z.object({
  loan_product_id: uuid,
  member_id: uuid,
  requested_amount: moneyString({ min: "0.01" }),
  requested_term_periods: z
    .number()
    .int("Must be a whole number of periods")
    .min(1, "At least one period")
    .max(360, "Term cannot exceed 360 periods"),
  purpose: z.string().trim().min(10, "Purpose required").max(500),
  disbursement_destination: disbursementDestinationSchema,
  disbursement_account_id: uuid.optional(),
  idempotency_key: idempotencyKey,
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
  "interest_only_period",
  "principal_holiday",
]);

export const loanRestructureSchema = z.object({
  restructuring_type: restructuringTypeSchema,
  periods_added: z
    .number()
    .int()
    .min(1, "Must add at least one period")
    .max(120, "Cannot add more than 120 periods"),
  reason: z.string().trim().min(20, "Reason must be at least 20 chars").max(1000),
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
  repayment_frequency: z.enum(["monthly", "quarterly", "annual"]),
  max_term_periods: z.number().int().min(1).max(360),
  min_amount: moneyString({ min: "0" }),
  max_amount: moneyString({ min: "0" }),
  required_approvals: z.number().int().min(1).max(5),
  // Detail fields (GL account codes, write_off_threshold) accept simple
  // string IDs from the backend's product service.
  gl_principal_receivable_code: z.string().trim().min(1).max(20),
  gl_interest_receivable_code: z.string().trim().min(1).max(20),
  gl_interest_income_code: z.string().trim().min(1).max(20),
  gl_loan_loss_expense_code: z.string().trim().min(1).max(20),
  penalty_fee_type_code: z.string().trim().max(40).optional().or(z.literal("")),
  write_off_threshold: moneyString({ min: "0" }).optional(),
  disbursement_destinations: z.array(disbursementDestinationSchema).min(1),
  repayment_allocation: z.enum(["principal_first", "interest_first", "fees_first"]),
});

export type LoanApplicationInput = z.infer<typeof loanApplicationSchema>;
export type LoanRepaymentInput = z.infer<typeof loanRepaymentSchema>;
export type DisburseInput = z.infer<typeof disburseSchema>;
export type LoanRestructureInput = z.infer<typeof loanRestructureSchema>;
export type LoanWriteOffInput = z.infer<typeof loanWriteOffSchema>;
export type LoanRecoveryInput = z.infer<typeof loanRecoverySchema>;
export type LoanProductInput = z.infer<typeof loanProductSchema>;
