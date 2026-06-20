import { describe, expect, it } from "vitest";
import {
  PLATFORM_OPERATION_LABELS,
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

describe("operationLabel", () => {
  it("returns the mapped label when known", () => {
    expect(operationLabel("tenant.suspend")).toBe("Suspend tenant");
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
