import { describe, expect, it } from "vitest";
import {
  PLATFORM_OPERATION_LABELS,
  TENANT_OPERATION_LABELS,
  approveActionSchema,
  operationLabel,
  rejectActionSchema,
} from "../approvals";

describe("PLATFORM_OPERATION_LABELS", () => {
  it("labels every known platform operation", () => {
    expect(PLATFORM_OPERATION_LABELS["billing.void_invoice"]).toBe("Void invoice");
    expect(PLATFORM_OPERATION_LABELS["platform_user.update_sensitive"]).toBe(
      "Update platform user",
    );
  });
});

describe("TENANT_OPERATION_LABELS", () => {
  it("labels every tenant operation", () => {
    expect(TENANT_OPERATION_LABELS["members.change_status"]).toBe("Change member status");
    expect(TENANT_OPERATION_LABELS["savings.withdraw"]).toBe("Withdraw from savings");
    expect(TENANT_OPERATION_LABELS["shares.redeem_shares"]).toBe("Redeem shares");
    expect(TENANT_OPERATION_LABELS["credit.approve_application"]).toBe("Approve loan application");
    expect(TENANT_OPERATION_LABELS["credit.write_off"]).toBe("Write off loan");
    expect(TENANT_OPERATION_LABELS["credit.restructure_schedule"]).toBe(
      "Restructure loan schedule",
    );
    expect(TENANT_OPERATION_LABELS["credit.apply_payroll_batch"]).toBe("Apply payroll batch");
    expect(TENANT_OPERATION_LABELS["ledger.post_journal_entry"]).toBe("Post manual GL entry");
  });
});

describe("operationLabel", () => {
  it("returns the mapped label when known", () => {
    expect(operationLabel("tenant.suspend")).toBe("Suspend tenant");
  });
  it("resolves tenant operations too", () => {
    expect(operationLabel("members.change_status")).toBe("Change member status");
    expect(operationLabel("ledger.post_journal_entry")).toBe("Post manual GL entry");
  });
  it("humanizes an unknown operation instead of rendering the raw key", () => {
    expect(operationLabel("widget.frobnicate_thing")).toBe("Frobnicate thing");
  });
});

describe("approveActionSchema", () => {
  it("accepts an empty body (comment optional)", () => {
    expect(approveActionSchema.parse({})).toEqual({});
  });
  it("accepts an optional comment", () => {
    expect(approveActionSchema.parse({ comment: "looks good" }).comment).toBe("looks good");
  });
});

describe("rejectActionSchema", () => {
  it("requires a reason of at least 10 chars", () => {
    expect(rejectActionSchema.safeParse({ reason: "too short" }).success).toBe(false);
    expect(rejectActionSchema.safeParse({ reason: "this is a valid reason" }).success).toBe(true);
  });
});
