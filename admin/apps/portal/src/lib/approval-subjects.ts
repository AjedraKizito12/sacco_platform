import type { ApprovalRequestOut } from "@sacco/schemas";

export interface ApprovalSubjectRule {
  operationType: string;
  payloadKey: string;
}

export const APPROVAL_SUBJECTS: Record<string, ApprovalSubjectRule[]> = {
  invoice: [{ operationType: "billing.void_invoice", payloadKey: "invoice_id" }],
  subscription: [
    { operationType: "billing.cancel_subscription", payloadKey: "subscription_id" },
  ],
  tenant: [
    { operationType: "tenant.suspend", payloadKey: "tenant_id" },
    { operationType: "tenant.retry_provisioning", payloadKey: "tenant_id" },
  ],
  platform_user: [
    { operationType: "platform_user.update_sensitive", payloadKey: "user_id" },
  ],
};

/**
 * The first pending approval whose operation_type + payload reference this
 * record. Pure — the caller passes already-fetched requests.
 */
export function findOpenApproval(
  entityType: string,
  recordId: string,
  pending: ApprovalRequestOut[],
): ApprovalRequestOut | null {
  const rules = APPROVAL_SUBJECTS[entityType];
  if (!rules) return null;
  for (const r of pending) {
    if (r.status !== "pending") continue;
    const rule = rules.find((x) => x.operationType === r.operation_type);
    if (!rule) continue;
    if (r.payload[rule.payloadKey] === recordId) return r;
  }
  return null;
}
