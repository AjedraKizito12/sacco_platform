import { describe, expect, it } from "vitest";
import {
  shareProductSchema,
  purchaseSharesSchema,
  type ShareAccountListItemOut,
} from "../shares";

describe("shares schemas + read types", () => {
  it("product schema rejects a blank name", () => {
    expect(
      shareProductSchema.safeParse({
        name: "",
        par_value: "1000",
        minimum_shares: "1",
        share_capital_account_id: "11111111-1111-1111-1111-111111111111",
      }).success,
    ).toBe(false);
  });
  it("product schema accepts a valid product without maximum_shares", () => {
    expect(
      shareProductSchema.safeParse({
        name: "Ordinary Shares",
        par_value: "1000.00",
        minimum_shares: "1",
        share_capital_account_id: "11111111-1111-1111-1111-111111111111",
      }).success,
    ).toBe(true);
  });
  it("purchase schema rejects a zero quantity", () => {
    expect(
      purchaseSharesSchema.safeParse({
        quantity: "0",
        payment_account_id: "11111111-1111-1111-1111-111111111111",
        idempotency_key: "abcd1234efgh",
      }).success,
    ).toBe(false);
  });
  it("ShareAccountListItemOut is structurally usable", () => {
    const a: ShareAccountListItemOut = {
      id: "a1",
      member_id: "m1",
      share_product_id: "p1",
      product_name: "Ordinary Shares",
      par_value: "1000.00",
      shares_held: 5,
      total_value: "5000.00",
    };
    expect(a.shares_held).toBe(5);
  });
});
