import { describe, expect, it } from "vitest";
import type {
  TrialBalanceOut,
  LoanPortfolioOut,
  ReportRunOut,
} from "../reporting";

describe("reporting read types", () => {
  it("are structurally usable", () => {
    const tb: TrialBalanceOut = {
      as_of_date: "2026-06-01",
      generated_at: "2026-06-01T00:00:00Z",
      lines: [
        {
          account_id: "a1",
          account_code: "1000",
          account_name: "Cash",
          account_type: "asset",
          debit_total: "100.0000",
          credit_total: "0.0000",
          balance: "100.0000",
        },
      ],
    };
    const lp: LoanPortfolioOut = {
      as_of_date: "2026-06-01",
      generated_at: "2026-06-01T00:00:00Z",
      rows: [
        {
          loan_id: "l1",
          loan_reference: "LN-1",
          member_id: "m1",
          product_name: "Personal",
          disbursed_at: "2026-01-01",
          maturity_date: null,
          status: "disbursed",
          outstanding_principal: "900.0000",
          accrued_interest: "0.0000",
          total_written_off: "0.0000",
          days_in_arrears: 0,
          aging_bucket: "current",
        },
      ],
    };
    const run: ReportRunOut = {
      id: "r1",
      report_type: "trial_balance",
      as_of_date: "2026-06-01",
      status: "done",
      started_at: "2026-06-01T00:00:00Z",
      completed_at: null,
      error_detail: null,
    };
    expect(tb.lines[0]!.balance).toBe("100.0000");
    expect(lp.rows[0]!.days_in_arrears).toBe(0);
    expect(run.status).toBe("done");
  });
});
