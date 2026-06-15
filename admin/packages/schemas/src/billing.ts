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

// Tenant-context assign-plan body (tenant_id comes from the URL path).
// Mirrors AssignPlanIn in app/platform_/tenants/schemas.py.
export const assignPlanSchema = z.object({
  // Inline uuid (not the shared `uuid` helper) so the empty-default Select
  // surfaces a natural "Select a plan" message on submit.
  plan_id: z.string().uuid("Select a plan"),
  start_date: isoDate.optional(),
});
export type AssignPlanInput = z.infer<typeof assignPlanSchema>;

// ── Read models (hand-written, mirror app/platform_/billing/schemas.py) ──────

export interface SubscriptionPlanOut {
  id: string;
  code: string;
  name: string;
  description: string | null;
  currency: string;
  base_price: string;
  per_user_price: string;
  per_member_price: string;
  billing_period: "monthly" | "quarterly" | "annual";
  member_limit: number | null;
  user_limit: number | null;
  features: Record<string, unknown>;
  trial_period_days: number;
  grace_period_days: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionOut {
  id: string;
  tenant_id: string;
  plan_id: string;
  status: string;
  started_at: string;
  current_period_start: string;
  current_period_end: string;
  grace_period_ends_at: string | null;
  cancelled_at: string | null;
  cancellation_reason: string | null;
  next_billing_date: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export type RecordPaymentInput = z.infer<typeof recordPaymentSchema>;
export type SubscriptionPlanInput = z.infer<typeof subscriptionPlanSchema>;
export type SubscriptionPlanPatchInput = z.infer<typeof subscriptionPlanPatchSchema>;
export type SubscriptionCreateInput = z.infer<typeof subscriptionCreateSchema>;
export type SubscriptionCancelInput = z.infer<typeof subscriptionCancelSchema>;
export type InvoiceVoidInput = z.infer<typeof invoiceVoidSchema>;
export type PaymentRejectInput = z.infer<typeof paymentRejectSchema>;

export const PAYMENT_METHOD_OPTIONS = [
  { value: "bank_transfer", label: "Bank transfer" },
  { value: "mobile_money", label: "Mobile money" },
  { value: "cash", label: "Cash" },
  { value: "cheque", label: "Cheque" },
] as const;

// ── Read models (hand-written, mirror app/platform_/billing/schemas.py) ──────

export interface InvoiceLineItemOut {
  id: string;
  invoice_id: string;
  description: string;
  quantity: number;
  unit_price: string;
  amount: string;
  line_order: number;
}

export interface InvoiceOut {
  id: string;
  invoice_number: string;
  subscription_id: string;
  tenant_id: string;
  billing_period_start: string;
  billing_period_end: string;
  amount_subtotal: string;
  amount_tax: string;
  amount_total: string;
  amount_paid: string;
  currency: string;
  status: string;
  issued_at: string | null;
  due_at: string;
  paid_at: string | null;
  voided_at: string | null;
  void_reason: string | null;
  pdf_storage_key: string | null;
  created_at: string;
  updated_at: string;
}

export interface InvoiceDetailOut extends InvoiceOut {
  line_items: InvoiceLineItemOut[];
}

export interface PaymentOut {
  id: string;
  invoice_id: string;
  amount: string;
  currency: string;
  payment_method: string;
  external_reference: string | null;
  notes: string | null;
  recorded_by: string;
  recorded_at: string;
  approval_request_id: string | null;
  status: string;
  confirmed_at: string | null;
}
