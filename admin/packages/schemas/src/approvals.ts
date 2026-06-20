import { z } from "zod";

// ── Read models (hand-written, mirror app/modules/maker_checker/schemas.py) ──

export interface ApprovalActionOut {
  id: string;
  actor_user_id: string;
  action: string; // "approve" | "reject"
  acted_at: string;
  comment: string | null;
}

export interface ApprovalRequestOut {
  id: string;
  operation_type: string;
  payload: Record<string, unknown>;
  requested_by: string;
  requested_at: string;
  required_approvals: number;
  current_approvals: number;
  status: string;
  expires_at: string | null;
  executed_at: string | null;
  execution_result: Record<string, unknown> | null;
  rejection_reason: string | null;
}

export interface ApprovalRequestDetailOut extends ApprovalRequestOut {
  actions: ApprovalActionOut[];
}

// ── Operation labels ─────────────────────────────────────────────────────────

export const PLATFORM_OPERATION_LABELS: Record<string, string> = {
  "platform_user.update_sensitive": "Update platform user",
  "billing.void_invoice": "Void invoice",
  "billing.cancel_subscription": "Cancel subscription",
  "billing.confirm_payment": "Confirm payment",
  "tenant.suspend": "Suspend tenant",
  "tenant.retry_provisioning": "Retry provisioning",
  "platform.start_impersonation": "Start impersonation",
};

/**
 * Human label for an operation type. Falls back to humanizing the last
 * dot-segment so a new backend operation never renders a raw key badly
 * (mirrors StatusBadge unknown-status behavior, CLAUDE.md contract S).
 */
export function operationLabel(operationType: string): string {
  const known = PLATFORM_OPERATION_LABELS[operationType];
  if (known) return known;
  const tail = operationType.split(".").pop() ?? operationType;
  const words = tail.replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

// ── Action inputs ────────────────────────────────────────────────────────────

export const approveActionSchema = z.object({
  comment: z.string().optional(),
});
export type ApproveActionInput = z.infer<typeof approveActionSchema>;

export const rejectActionSchema = z.object({
  reason: z.string().min(10, "Provide a reason of at least 10 characters."),
});
export type RejectActionInput = z.infer<typeof rejectActionSchema>;
