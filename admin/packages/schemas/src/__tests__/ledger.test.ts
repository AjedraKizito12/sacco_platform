import { describe, expect, it } from "vitest";
import {
  manualJournalEntrySchema,
  type AccountWithBalanceOut,
  type JournalEntryOut,
} from "../ledger";

const U = "550e8400-e29b-41d4-a716-446655440000";
const V = "550e8400-e29b-41d4-a716-446655440001";

describe("ledger schemas", () => {
  const base = { reference: "JV-1", description: "Test", idempotency_key: "abcd1234efgh" };

  it("rejects unbalanced lines", () => {
    expect(
      manualJournalEntrySchema.safeParse({
        ...base,
        lines: [
          { account_id: U, debit_amount: "100", credit_amount: "0" },
          { account_id: V, debit_amount: "0", credit_amount: "50" },
        ],
      }).success,
    ).toBe(false);
  });

  it("rejects a line with both a debit and a credit", () => {
    expect(
      manualJournalEntrySchema.safeParse({
        ...base,
        lines: [
          { account_id: U, debit_amount: "100", credit_amount: "100" },
          { account_id: V, debit_amount: "0", credit_amount: "100" },
        ],
      }).success,
    ).toBe(false);
  });

  it("accepts a balanced pair", () => {
    expect(
      manualJournalEntrySchema.safeParse({
        ...base,
        lines: [
          { account_id: U, debit_amount: "100", credit_amount: "0" },
          { account_id: V, debit_amount: "0", credit_amount: "100" },
        ],
      }).success,
    ).toBe(true);
  });

  it("read types are structurally usable", () => {
    const a: AccountWithBalanceOut = {
      id: "a1", code: "1000", name: "Cash", account_type: "asset", parent_id: null,
      is_active: true, description: null, created_at: "t", updated_at: "t", balance: "100.0000",
    };
    const e: JournalEntryOut = {
      id: "e1", reference: "JV-1", description: "Test", posted_by: "u1", posted_at: "t",
      idempotency_key: "k",
      lines: [
        { id: "l1", account_id: "a1", debit_amount: "100.0000", credit_amount: "0.0000", description: null },
      ],
    };
    expect(a.balance).toBe("100.0000");
    expect(e.lines.length).toBe(1);
  });
});
