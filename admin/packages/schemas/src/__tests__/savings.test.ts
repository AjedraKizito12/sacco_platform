// admin/packages/schemas/src/__tests__/savings.test.ts
import { describe, expect, it } from "vitest";
import { depositSchema, openAccountSchema, withdrawSchema } from "../savings";

describe("openAccountSchema", () => {
  it("requires both UUIDs", () => {
    expect(() =>
      openAccountSchema.parse({
        member_id: "550e8400-e29b-41d4-a716-446655440000",
        savings_product_id: "550e8400-e29b-41d4-a716-446655440001",
      }),
    ).not.toThrow();
  });
});

describe("depositSchema", () => {
  const ok = {
    amount: "50000.00",
    payment_account_id: "550e8400-e29b-41d4-a716-446655440002",
    idempotency_key: "1234567890ab",
  };
  it("accepts a valid deposit", () => {
    expect(() => depositSchema.parse(ok)).not.toThrow();
  });
  it("rejects zero amount", () => {
    expect(() =>
      depositSchema.parse({ ...ok, amount: "0" }),
    ).toThrow();
  });
  it("rejects float-precision overflow", () => {
    expect(() =>
      depositSchema.parse({ ...ok, amount: "50000.12345" }),
    ).toThrow();
  });
  it("rejects short idempotency key", () => {
    expect(() =>
      depositSchema.parse({ ...ok, idempotency_key: "short" }),
    ).toThrow();
  });
});

describe("withdrawSchema", () => {
  it("uses the same shape as deposit", () => {
    expect(withdrawSchema.shape.amount).toBe(depositSchema.shape.amount);
  });
});
