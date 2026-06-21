import type { FetchClient } from "../client";

export function savings(api: FetchClient) {
  return {
    listProducts: (query?: Record<string, unknown>) =>
      api.GET("/savings/products" as never, { params: { query } } as never),
    createProduct: (body: Record<string, unknown>) =>
      api.POST("/savings/products" as never, { body } as never),
    getProduct: (id: string) =>
      api.GET("/savings/products/{product_id}" as never, {
        params: { path: { product_id: id } },
      } as never),
    listAccounts: (query?: Record<string, unknown>) =>
      api.GET("/savings/accounts" as never, { params: { query } } as never),
    createAccount: (body: Record<string, unknown>) =>
      api.POST("/savings/accounts" as never, { body } as never),
    getAccount: (id: string) =>
      api.GET("/savings/accounts/{account_id}" as never, {
        params: { path: { account_id: id } },
      } as never),
    deposit: (id: string, body: Record<string, unknown>) =>
      api.POST("/savings/accounts/{account_id}/deposit" as never, {
        params: { path: { account_id: id } },
        body,
      } as never),
    withdraw: (id: string, body: Record<string, unknown>) =>
      api.POST("/savings/accounts/{account_id}/withdraw" as never, {
        params: { path: { account_id: id } },
        body,
      } as never),
    listTransactions: (id: string, query?: Record<string, unknown>) =>
      api.GET("/savings/accounts/{account_id}/transactions" as never, {
        params: { path: { account_id: id }, query },
      } as never),
  } as const;
}
