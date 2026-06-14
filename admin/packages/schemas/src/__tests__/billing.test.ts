// admin/packages/schemas/src/__tests__/billing.test.ts
import { describe, expect, it } from "vitest";
import {
  assignPlanSchema,
  recordPaymentSchema,
  subscriptionPlanPatchSchema,
  subscriptionPlanSchema,
} from "../billing";

describe("recordPaymentSchema", () => {
  const ok = {
    amount: "50000.00",
    currency: "UGX",
    payment_method: "bank_transfer" as const,
    idempotency_key: "12345678",
  };

  it("accepts a valid payment", () => {
    expect(() => recordPaymentSchema.parse(ok)).not.toThrow();
  });

  it("defaults currency to UGX when omitted", () => {
    const { currency, ...rest } = ok;
    void currency;
    const parsed = recordPaymentSchema.parse(rest);
    expect(parsed.currency).toBe("UGX");
  });

  it("rejects invalid payment_method", () => {
    expect(() =>
      recordPaymentSchema.parse({
        ...ok,
        payment_method: "crypto" as never,
      }),
    ).toThrow();
  });

  it("rejects too-short idempotency_key", () => {
    expect(() =>
      recordPaymentSchema.parse({ ...ok, idempotency_key: "short" }),
    ).toThrow();
  });
});

describe("subscriptionPlanSchema", () => {
  it("requires a code matching the slug pattern", () => {
    expect(() =>
      subscriptionPlanSchema.parse({
        code: "Starter Plan",
        name: "Starter",
        base_price: "0",
        billing_period: "monthly",
      }),
    ).toThrow();
  });

  it("applies defaults for per_user_price + grace_period_days", () => {
    const plan = subscriptionPlanSchema.parse({
      code: "starter",
      name: "Starter",
      base_price: "50000",
      billing_period: "monthly",
    });
    expect(plan.per_user_price).toBe("0");
    expect(plan.grace_period_days).toBe(30);
  });
});

describe("subscriptionPlanPatchSchema", () => {
  it("accepts a partial update", () => {
    expect(() =>
      subscriptionPlanPatchSchema.parse({ name: "Starter v2" }),
    ).not.toThrow();
  });

  it("rejects unknown keys (strict)", () => {
    expect(() =>
      subscriptionPlanPatchSchema.parse({ code: "cannot-change" }),
    ).toThrow();
  });
});

describe("assignPlanSchema", () => {
  it("accepts a plan_id alone", () => {
    expect(
      assignPlanSchema.safeParse({ plan_id: "11111111-1111-1111-1111-111111111111" })
        .success,
    ).toBe(true);
  });
  it("accepts a plan_id with an ISO start_date", () => {
    expect(
      assignPlanSchema.safeParse({
        plan_id: "11111111-1111-1111-1111-111111111111",
        start_date: "2026-07-01",
      }).success,
    ).toBe(true);
  });
  it("rejects a missing plan_id", () => {
    expect(assignPlanSchema.safeParse({ start_date: "2026-07-01" }).success).toBe(false);
  });
  it("rejects a non-uuid plan_id", () => {
    expect(assignPlanSchema.safeParse({ plan_id: "nope" }).success).toBe(false);
  });
});
