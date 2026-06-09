import type { FetchClient } from "../client";

export function reporting(api: FetchClient) {
  return {
    loanPortfolio: (query?: Record<string, unknown>) =>
      api.GET("/reporting/loan-portfolio" as never, { params: { query } } as never),
    incomeStatement: (query?: Record<string, unknown>) =>
      api.GET("/reporting/income-statement" as never, { params: { query } } as never),
    savingsStatement: (query?: Record<string, unknown>) =>
      api.GET("/reporting/savings-statement" as never, { params: { query } } as never),
    feeCollection: (query?: Record<string, unknown>) =>
      api.GET("/reporting/fee-collection" as never, { params: { query } } as never),
    trialBalance: (query?: Record<string, unknown>) =>
      api.GET("/reporting/trial-balance" as never, { params: { query } } as never),
    listRuns: (query?: Record<string, unknown>) =>
      api.GET("/reporting/runs" as never, { params: { query } } as never),
  } as const;
}
