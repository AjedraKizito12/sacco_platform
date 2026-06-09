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
  "scheduled",
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
  target_type: z.enum(["member", "loan", "savings_account"]),
  target_id: uuid,
  period_start: isoDate,
  period_end: isoDate,
});

export const feeCollectionSchema = z
  .object({
    fee_assessment_id: uuid,
    amount: moneyString({ min: "0.01" }),
    method: z.enum(["cash", "journal_voucher"]),
    contra_account_id: uuid.optional(),
    idempotency_key: idempotencyKey,
  })
  .refine(
    (data) =>
      data.method !== "journal_voucher" || data.contra_account_id !== undefined,
    {
      message: "contra_account_id is required for journal_voucher",
      path: ["contra_account_id"],
    },
  );

export type FeeTypeInput = z.infer<typeof feeTypeSchema>;
export type FeeTypePatchInput = z.infer<typeof feeTypePatchSchema>;
export type FeeAssessmentInput = z.infer<typeof feeAssessmentSchema>;
export type FeeCollectionInput = z.infer<typeof feeCollectionSchema>;
