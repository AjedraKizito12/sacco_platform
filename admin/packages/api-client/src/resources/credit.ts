import type { FetchClient } from "../client";

export function credit(api: FetchClient) {
  return {
    // Applications
    listApplications: (query?: Record<string, unknown>) =>
      api.GET("/credit/applications" as never, { params: { query } } as never),
    createApplication: (body: Record<string, unknown>) =>
      api.POST("/credit/applications" as never, { body } as never),
    getApplication: (id: string) =>
      api.GET("/credit/applications/{application_id}" as never, {
        params: { path: { application_id: id } },
      } as never),
    approveApplication: (id: string, body: Record<string, unknown>) =>
      api.POST("/credit/applications/{application_id}/approve" as never, {
        params: { path: { application_id: id } },
        body,
      } as never),
    rejectApplication: (id: string, body: Record<string, unknown>) =>
      api.POST("/credit/applications/{application_id}/reject" as never, {
        params: { path: { application_id: id } },
        body,
      } as never),
    withdrawApplication: (id: string, body: Record<string, unknown>) =>
      api.POST("/credit/applications/{application_id}/withdraw" as never, {
        params: { path: { application_id: id } },
        body,
      } as never),

    // Guarantors
    listGuarantors: (applicationId: string) =>
      api.GET("/credit/applications/{application_id}/guarantors" as never, {
        params: { path: { application_id: applicationId } },
      } as never),
    addGuarantor: (applicationId: string, body: Record<string, unknown>) =>
      api.POST("/credit/applications/{application_id}/guarantors" as never, {
        params: { path: { application_id: applicationId } },
        body,
      } as never),
    acceptGuarantor: (guarantorId: string, body: Record<string, unknown>) =>
      api.POST("/credit/guarantors/{guarantor_id}/accept" as never, {
        params: { path: { guarantor_id: guarantorId } },
        body,
      } as never),
    declineGuarantor: (guarantorId: string, body: Record<string, unknown>) =>
      api.POST("/credit/guarantors/{guarantor_id}/decline" as never, {
        params: { path: { guarantor_id: guarantorId } },
        body,
      } as never),

    // Loans
    listLoans: (query?: Record<string, unknown>) =>
      api.GET("/credit/loans" as never, { params: { query } } as never),
    disburse: (applicationId: string, body: Record<string, unknown>) =>
      api.POST("/credit/loans/{application_id}/disburse" as never, {
        params: { path: { application_id: applicationId } },
        body,
      } as never),
    getLoan: (id: string) =>
      api.GET("/credit/loans/{loan_id}" as never, {
        params: { path: { loan_id: id } },
      } as never),
    getSchedule: (id: string) =>
      api.GET("/credit/loans/{loan_id}/schedule" as never, {
        params: { path: { loan_id: id } },
      } as never),
    getStatement: (id: string, query?: Record<string, unknown>) =>
      api.GET("/credit/loans/{loan_id}/statement" as never, {
        params: { path: { loan_id: id }, query },
      } as never),
    getStatementPdf: (id: string, query?: Record<string, unknown>) =>
      api.GET("/credit/loans/{loan_id}/statement.pdf" as never, {
        params: { path: { loan_id: id }, query },
      } as never),
    listRepayments: (id: string, query?: Record<string, unknown>) =>
      api.GET("/credit/loans/{loan_id}/repayments" as never, {
        params: { path: { loan_id: id }, query },
      } as never),
    recordRepayment: (id: string, body: Record<string, unknown>) =>
      api.POST("/credit/loans/{loan_id}/repayments" as never, {
        params: { path: { loan_id: id } },
        body,
      } as never),
    writeOff: (id: string, body: Record<string, unknown>) =>
      api.POST("/credit/loans/{loan_id}/write-off" as never, {
        params: { path: { loan_id: id } },
        body,
      } as never),
    recover: (id: string, body: Record<string, unknown>) =>
      api.POST("/credit/loans/{loan_id}/recover" as never, {
        params: { path: { loan_id: id } },
        body,
      } as never),
    restructure: (id: string, body: Record<string, unknown>) =>
      api.POST("/credit/loans/{loan_id}/restructure" as never, {
        params: { path: { loan_id: id } },
        body,
      } as never),
    listRestructurings: (id: string) =>
      api.GET("/credit/loans/{loan_id}/restructurings" as never, {
        params: { path: { loan_id: id } },
      } as never),

    // Products
    listProducts: (query?: Record<string, unknown>) =>
      api.GET("/credit/products" as never, { params: { query } } as never),
    createProduct: (body: Record<string, unknown>) =>
      api.POST("/credit/products" as never, { body } as never),
    getProduct: (id: string) =>
      api.GET("/credit/products/{product_id}" as never, {
        params: { path: { product_id: id } },
      } as never),
    patchProduct: (id: string, body: Record<string, unknown>) =>
      api.PATCH("/credit/products/{product_id}" as never, {
        params: { path: { product_id: id } },
        body,
      } as never),

    // Payroll batches
    createPayrollBatch: (body: Record<string, unknown>) =>
      api.POST("/credit/payroll-batches" as never, { body } as never),
    createPayrollBatchFromCsv: (body: Record<string, unknown>) =>
      api.POST("/credit/payroll-batches/csv" as never, { body } as never),
    getPayrollBatch: (id: string) =>
      api.GET("/credit/payroll-batches/{batch_id}" as never, {
        params: { path: { batch_id: id } },
      } as never),
    rejectPayrollBatch: (id: string, body: Record<string, unknown>) =>
      api.POST("/credit/payroll-batches/{batch_id}/reject" as never, {
        params: { path: { batch_id: id } },
        body,
      } as never),

    // Queries
    loansEligibleForFee: (query?: Record<string, unknown>) =>
      api.GET("/credit/query/loans-eligible-for-fee" as never, {
        params: { query },
      } as never),
  } as const;
}
