import type { FetchClient } from "../client";

export function member(api: FetchClient) {
  return {
    listSavings: (query?: Record<string, unknown>) =>
      api.GET("/member/savings" as never, { params: { query } } as never),
    getSavingsTransactions: (accountId: string) =>
      api.GET("/member/savings/{account_id}/transactions" as never, {
        params: { path: { account_id: accountId } },
      } as never),
    listShares: (query?: Record<string, unknown>) =>
      api.GET("/member/shares" as never, { params: { query } } as never),
    listLoans: (query?: Record<string, unknown>) =>
      api.GET("/member/loans" as never, { params: { query } } as never),
    getLoan: (loanId: string) =>
      api.GET("/member/loans/{loan_id}" as never, {
        params: { path: { loan_id: loanId } },
      } as never),
    getLoanSchedule: (loanId: string) =>
      api.GET("/member/loans/{loan_id}/schedule" as never, {
        params: { path: { loan_id: loanId } },
      } as never),
    getLoanStatement: (loanId: string) =>
      api.GET("/member/loans/{loan_id}/statement" as never, {
        params: { path: { loan_id: loanId } },
      } as never),
    listFees: (query?: Record<string, unknown>) =>
      api.GET("/member/fees" as never, { params: { query } } as never),
    listLoanApplications: (query?: Record<string, unknown>) =>
      api.GET("/member/loan-applications" as never, { params: { query } } as never),
    getLoanApplication: (applicationId: string) =>
      api.GET("/member/loan-applications/{application_id}" as never, {
        params: { path: { application_id: applicationId } },
      } as never),
    getMyKyc: () => api.GET("/member/me/kyc" as never),
  } as const;
}
