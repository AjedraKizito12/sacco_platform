import { describe, expect, it } from "vitest";
import type { ApprovalRequestOut } from "@sacco/schemas";
import { findOpenApproval } from "../../lib/approval-subjects";

function req(over: Partial<ApprovalRequestOut>): ApprovalRequestOut {
  return {
    id: "ar1",
    operation_type: "billing.void_invoice",
    payload: { invoice_id: "inv1" },
    requested_by: "u1",
    requested_at: "2026-06-20T10:00:00Z",
    required_approvals: 1,
    current_approvals: 0,
    status: "pending",
    expires_at: null,
    executed_at: null,
    execution_result: null,
    rejection_reason: null,
    ...over,
  };
}

describe("findOpenApproval", () => {
  it("matches an invoice void by invoice_id", () => {
    expect(findOpenApproval("invoice", "inv1", [req({})])?.id).toBe("ar1");
  });
  it("returns null when the record id does not match the payload", () => {
    expect(findOpenApproval("invoice", "other", [req({})])).toBeNull();
  });
  it("ignores non-pending requests", () => {
    expect(findOpenApproval("invoice", "inv1", [req({ status: "executed" })])).toBeNull();
  });
  it("matches both tenant operation rules on tenant_id", () => {
    const suspend = req({
      id: "a",
      operation_type: "tenant.suspend",
      payload: { tenant_id: "t1" },
    });
    const retry = req({
      id: "b",
      operation_type: "tenant.retry_provisioning",
      payload: { tenant_id: "t1" },
    });
    expect(findOpenApproval("tenant", "t1", [retry])?.id).toBe("b");
    expect(findOpenApproval("tenant", "t1", [suspend])?.id).toBe("a");
  });
  it("returns null for an entity with no rules", () => {
    expect(findOpenApproval("loan", "x", [req({})])).toBeNull();
  });
});
