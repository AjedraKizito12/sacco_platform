// admin/packages/schemas/src/fees.ts
import { z } from "zod";
import { currencyCode, idempotencyKey, isoDate, moneyString, uuid } from "./common";

export const feeApplicableToSchema = z.enum([
  "member",
  "loan",
  "savings_account",
  "share_account",
]);

export const feeAmountKindSchema = z.enum([
  "fixed",
  "percentage",
  "tiered",
]);

export const feeTriggerKindSchema = z.enum([
  "event",
  "schedule",
  "manual",
]);

export const feeTypeSchema = z.object({
  code: z
    .string()
    .trim()
    .min(1)
    .max(40)
    .regex(/^[a-z0-9_]+$/, "Use lowercase, digits, or _"),
  name: z.string().trim().min(1).max(200),
  description: z.string().trim().max(1000).optional().or(z.literal("")),
  applicable_to: feeApplicableToSchema,
  amount_kind: feeAmountKindSchema,
  amount: moneyString({ min: "0" }),
  currency: currencyCode.default("UGX"),
  trigger_kind: feeTriggerKindSchema,
  event_name: z.string().trim().max(100).optional().or(z.literal("")),
  schedule_config: z.record(z.string(), z.unknown()).optional(),
  gl_income_account_code: z.string().trim().min(1).max(20),
  gl_receivable_account_code: z.string().trim().min(1).max(20),
  requires_collection: z.boolean().default(true),
});

export const feeTypePatchSchema = z
  .object({
    name: z.string().trim().min(1).max(200).optional(),
    description: z.string().trim().max(1000).optional().or(z.literal("")),
    amount: moneyString({ min: "0" }).optional(),
    is_active: z.boolean().optional(),
    requires_collection: z.boolean().optional(),
  })
  .strict();

export const feeAssessmentSchema = z.object({
  fee_type_id: uuid,
  target_type: z.enum(["member", "loan", "savings_account", "share_account"]),
  target_id: uuid,
  period_start: isoDate,
  period_end: isoDate.optional().or(z.literal("")),
});

export const feeCollectionSchema = z.object({
  fee_assessment_id: uuid,
  amount: moneyString({ min: "0.01" }),
  method: z.enum(["cash", "journal_voucher"]),
  contra_account_id: uuid,
  idempotency_key: idempotencyKey,
});

export type FeeTypeInput = z.infer<typeof feeTypeSchema>;
export type FeeTypePatchInput = z.infer<typeof feeTypePatchSchema>;
export type FeeAssessmentInput = z.infer<typeof feeAssessmentSchema>;
export type FeeCollectionInput = z.infer<typeof feeCollectionSchema>;

// Mirror app/modules/fees/schemas.py. Decimals are JSON strings.
export interface FeeTypeOut {
  id: string;
  code: string;
  name: string;
  description: string | null;
  applicable_to: string;
  amount_kind: string;
  amount: string;
  percentage_basis: string | null;
  percentage_rate: string | null;
  currency: string;
  trigger_kind: string;
  event_name: string | null;
  schedule_config: Record<string, unknown> | null;
  gl_income_account_code: string;
  gl_receivable_account_code: string;
  is_active: boolean;
  requires_collection: boolean;
}

export interface FeeCollectionOut {
  id: string;
  fee_assessment_id: string;
  amount: string;
  collected_at: string;
  method: string;
  collected_by: string;
  journal_entry_id: string;
  idempotency_key: string;
}

export interface FeeAssessmentOut {
  id: string;
  fee_type_id: string;
  target_type: string;
  target_id: string;
  period_start: string;
  period_end: string | null;
  amount: string;
  currency: string;
  status: string;
  assessed_at: string;
  due_at: string | null;
  paid_at: string | null;
  waived_by: string | null;
  waiver_reason: string | null;
  journal_entry_id: string;
}

export interface FeeAssessmentDetailOut extends FeeAssessmentOut {
  collections: FeeCollectionOut[];
}
