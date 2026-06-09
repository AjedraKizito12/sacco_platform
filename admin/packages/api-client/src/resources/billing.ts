import type { FetchClient } from "../client";

export function billing(api: FetchClient) {
  return {
    // Platform context — plans
    listPlans: (query?: { only_active?: boolean }) =>
      api.GET("/platform/billing/plans" as never, { params: { query } } as never),
    createPlan: (body: Record<string, unknown>) =>
      api.POST("/platform/billing/plans" as never, { body } as never),
    getPlan: (planId: string) =>
      api.GET("/platform/billing/plans/{plan_id}" as never, {
        params: { path: { plan_id: planId } },
      } as never),
    patchPlan: (planId: string, body: Record<string, unknown>) =>
      api.PATCH("/platform/billing/plans/{plan_id}" as never, {
        params: { path: { plan_id: planId } },
        body,
      } as never),

    // Platform context — subscriptions
    listSubscriptions: (query?: Record<string, unknown>) =>
      api.GET("/platform/billing/subscriptions" as never, { params: { query } } as never),
    createSubscription: (body: Record<string, unknown>) =>
      api.POST("/platform/billing/subscriptions" as never, { body } as never),
    getSubscription: (id: string) =>
      api.GET("/platform/billing/subscriptions/{subscription_id}" as never, {
        params: { path: { subscription_id: id } },
      } as never),
    cancelSubscription: (
      id: string,
      query?: { mode?: "at_period_end" | "immediate" },
    ) =>
      api.POST("/platform/billing/subscriptions/{subscription_id}/cancel" as never, {
        params: { path: { subscription_id: id }, query },
      } as never),
    reactivateSubscription: (id: string) =>
      api.POST("/platform/billing/subscriptions/{subscription_id}/reactivate" as never, {
        params: { path: { subscription_id: id } },
      } as never),

    // Platform context — invoices
    listInvoices: (query?: Record<string, unknown>) =>
      api.GET("/platform/billing/invoices" as never, { params: { query } } as never),
    getInvoice: (id: string) =>
      api.GET("/platform/billing/invoices/{invoice_id}" as never, {
        params: { path: { invoice_id: id } },
      } as never),
    getInvoicePdf: (id: string) =>
      api.GET("/platform/billing/invoices/{invoice_id}.pdf" as never, {
        params: { path: { invoice_id: id } },
      } as never),
    voidInvoice: (id: string, body: Record<string, unknown>) =>
      api.POST("/platform/billing/invoices/{invoice_id}/void" as never, {
        params: { path: { invoice_id: id } },
        body,
      } as never),
    recordPayment: (id: string, body: Record<string, unknown>) =>
      api.POST("/platform/billing/invoices/{invoice_id}/payments" as never, {
        params: { path: { invoice_id: id } },
        body,
      } as never),

    // Platform context — payments
    listPendingPayments: () =>
      api.GET("/platform/billing/payments/pending-confirmation" as never),
    rejectPayment: (paymentId: string, body: Record<string, unknown>) =>
      api.POST("/platform/billing/payments/{payment_id}/reject" as never, {
        params: { path: { payment_id: paymentId } },
        body,
      } as never),

    // Tenant context — /billing/me/*
    mySubscription: () =>
      api.GET("/billing/me/subscription" as never),
    myInvoices: (query?: Record<string, unknown>) =>
      api.GET("/billing/me/invoices" as never, { params: { query } } as never),
    myInvoice: (id: string) =>
      api.GET("/billing/me/invoices/{invoice_id}" as never, {
        params: { path: { invoice_id: id } },
      } as never),
    myInvoicePdf: (id: string) =>
      api.GET("/billing/me/invoices/{invoice_id}.pdf" as never, {
        params: { path: { invoice_id: id } },
      } as never),
  } as const;
}
