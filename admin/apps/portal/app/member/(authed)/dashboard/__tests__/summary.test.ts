import { describe, it, expect } from "vitest";
import { computeMemberSummary } from "../_components/summary";

describe("computeMemberSummary", () => {
  it("derives totals, active/arrears loans, and outstanding fees", () => {
    const summary = computeMemberSummary({
      savings: [
        { available_balance: "1000.00", balance: "1200.00" },
        { balance: "500.00" }, // no lien field → falls back to balance
      ],
      shares: [
        { shares_held: 100, total_value: "1000000.00" },
        { shares_held: 20, total_value: "200000.00" },
      ],
      loans: [
        { status: "disbursed" },
        { status: "in_arrears" },
        { status: "closed" }, // not active
      ],
      fees: [
        { status: "pending", amount: "5000.00" },
        { status: "overdue", amount: "3000.00" },
        { status: "paid", amount: "9999.00" }, // settled → excluded
        { status: "waived", amount: "1000.00" }, // waived → excluded
      ],
    });

    expect(summary.savingsTotal).toBe("1500.00"); // 1000 (available) + 500
    expect(summary.sharesHeld).toBe(120);
    expect(summary.sharesValue).toBe("1200000.00");
    expect(summary.activeLoans).toBe(2); // disbursed + in_arrears
    expect(summary.loansInArrears).toBe(1);
    expect(summary.feesOutstanding).toBe("8000.00"); // 5000 + 3000
  });

  it("returns zeroed values for empty inputs", () => {
    const summary = computeMemberSummary({
      savings: [],
      shares: [],
      loans: [],
      fees: [],
    });
    expect(summary.savingsTotal).toBe("0.00");
    expect(summary.sharesHeld).toBe(0);
    expect(summary.sharesValue).toBe("0.00");
    expect(summary.activeLoans).toBe(0);
    expect(summary.loansInArrears).toBe(0);
    expect(summary.feesOutstanding).toBe("0.00");
  });
});
