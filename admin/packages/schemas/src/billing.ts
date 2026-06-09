// admin/packages/schemas/src/billing.ts
import { z } from "zod";
import {
  currencyCode,
  idempotencyKey,
  isoDate,
  moneyString,
  uuid,
} from "./common";

export const paymentMethodSchema = z.enum([
  "bank_transfer",
  "mobile_money",
  "cash",
  "cheque",
]);

export const recordPaymentSchema = z.object({
  amount: moneyString({ min: "0.01" }),
  currency: currencyCode.default("UGX"),
  payment_method: paymentMethodSchema,
  external_reference: z.string().trim().max(200).optional().or(z.literal("")),
  notes: z.string().trim().max(1000).optional().or(z.literal("")),
  idempotency_key: idempotencyKey,
});

export const billingPeriodSchema = z.enum(["monthly", "quarterly", "annual"]);

export const subscriptionPlanSchema = z.object({
  code: z
    .string()
    .trim()
    .min(1, "Code is required")
    .max(40)
    .regex(/^[a-z0-9_-]+$/, "Use lowercase, digits, _, or -"),
  name: z.string().trim().min(1).max(200),
  description: z.string().trim().max(1000).optional().or(z.literal("")),
  currency: currencyCode.default("UGX"),
  base_price: moneyString({ min: "0" }),
  per_user_price: moneyString({ min: "0" }).default("0"),
  per_member_price: moneyString({ min: "0" }).default("0"),
  billing_period: billingPeriodSchema,
  member_limit: z.number().int().min(0).optional(),
  user_limit: z.number().int().min(0).optional(),
  features: z.record(z.string(), z.unknown()).default({}),
  trial_period_days: z.number().int().min(0).max(365).default(0),
  grace_period_days: z.number().int().min(0).max(365).default(30),
});

// PATCH variant: all fields optional + code/billing_period are immutable.
export const subscriptionPlanPatchSchema = z
  .object({
    name: z.string().trim().min(1).max(200).optional(),
    description: z.string().trim().max(1000).optional().or(z.literal("")),
    base_price: moneyString({ min: "0" }).optional(),
    per_user_price: moneyString({ min: "0" }).optional(),
    per_member_price: moneyString({ min: "0" }).optional(),
    member_limit: z.number().int().min(0).optional(),
    user_limit: z.number().int().min(0).optional(),
    features: z.record(z.string(), z.unknown()).optional(),
    trial_period_days: z.number().int().min(0).max(365).optional(),
    grace_period_days: z.number().int().min(0).max(365).optional(),
    is_active: z.boolean().optional(),
  })
  .strict();

export const subscriptionCreateSchema = z.object({
  tenant_id: uuid,
  plan_id: uuid,
  start_date: isoDate.optional(),
});

export const subscriptionCancelSchema = z.object({
  reason: z.string().trim().min(10).max(500),
});

export const invoiceVoidSchema = z.object({
  reason: z.string().trim().min(10).max(500),
});

export const paymentRejectSchema = z.object({
  reason: z.string().trim().min(10).max(500),
});

export type RecordPaymentInput = z.infer<typeof recordPaymentSchema>;
export type SubscriptionPlanInput = z.infer<typeof subscriptionPlanSchema>;
export type SubscriptionPlanPatchInput = z.infer<typeof subscriptionPlanPatchSchema>;
export type SubscriptionCreateInput = z.infer<typeof subscriptionCreateSchema>;
export type SubscriptionCancelInput = z.infer<typeof subscriptionCancelSchema>;
export type InvoiceVoidInput = z.infer<typeof invoiceVoidSchema>;
export type PaymentRejectInput = z.infer<typeof paymentRejectSchema>;
