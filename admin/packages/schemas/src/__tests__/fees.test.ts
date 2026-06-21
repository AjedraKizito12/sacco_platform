import { describe, expect, it } from "vitest";
import {
  feeTriggerKindSchema,
  feeCollectionSchema,
  feeAssessmentSchema,
  type FeeTypeOut,
  type FeeAssessmentDetailOut,
} from "../fees";

const U = "550e8400-e29b-41d4-a716-446655440000";

describe("fees schemas (corrected to backend)", () => {
  it("trigger kind accepts schedule, rejects scheduled", () => {
    expect(feeTriggerKindSchema.safeParse("schedule").success).toBe(true);
    expect(feeTriggerKindSchema.safeParse("scheduled").success).toBe(false);
  });
  it("collection requires contra_account_id for cash", () => {
    expect(
      feeCollectionSchema.safeParse({
        fee_assessment_id: U,
        amount: "5000",
        method: "cash",
        idempotency_key: "abcd1234efgh",
      }).success,
    ).toBe(false);
    expect(
      feeCollectionSchema.safeParse({
        fee_assessment_id: U,
        amount: "5000",
        method: "cash",
        contra_account_id: U,
        idempotency_key: "abcd1234efgh",
      }).success,
    ).toBe(true);
  });
  it("assessment period_end is optional and share_account is a valid target", () => {
    expect(
      feeAssessmentSchema.safeParse({
        fee_type_id: U,
        target_type: "share_account",
        target_id: U,
        period_start: "2026-06-01",
      }).success,
    ).toBe(true);
  });
  it("read types are structurally usable", () => {
    const t: FeeTypeOut = {
      id: "f1",
      code: "annual",
      name: "Annual Fee",
      description: null,
      applicable_to: "member",
      amount_kind: "fixed",
      amount: "20000.0000",
      percentage_basis: null,
      percentage_rate: null,
      currency: "UGX",
      trigger_kind: "schedule",
      event_name: null,
      schedule_config: null,
      gl_income_account_code: "4200",
      gl_receivable_account_code: "1300",
      is_active: true,
      requires_collection: false,
    };
    const a: FeeAssessmentDetailOut = {
      id: "a1",
      fee_type_id: "f1",
      target_type: "member",
      target_id: "m1",
      period_start: "2026-06-01",
      period_end: null,
      amount: "20000.0000",
      currency: "UGX",
      status: "assessed",
      assessed_at: "2026-06-01T00:00:00Z",
      due_at: null,
      paid_at: null,
      waived_by: null,
      waiver_reason: null,
      journal_entry_id: "j1",
      collections: [],
    };
    expect(t.code).toBe("annual");
    expect(a.collections.length).toBe(0);
  });
});
