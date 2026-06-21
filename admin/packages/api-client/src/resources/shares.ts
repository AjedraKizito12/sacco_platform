import type { FetchClient } from "../client";

export function shares(api: FetchClient) {
  return {
    listProducts: (query?: Record<string, unknown>) =>
      api.GET("/shares/products" as never, { params: { query } } as never),
    createProduct: (body: Record<string, unknown>) =>
      api.POST("/shares/products" as never, { body } as never),
    getProduct: (id: string) =>
      api.GET("/shares/products/{product_id}" as never, {
        params: { path: { product_id: id } },
      } as never),
    listAccounts: (query?: Record<string, unknown>) =>
      api.GET("/shares/accounts" as never, { params: { query } } as never),
    openAccount: (body: Record<string, unknown>) =>
      api.POST("/shares/accounts" as never, { body } as never),
    getAccount: (id: string) =>
      api.GET("/shares/accounts/{account_id}" as never, {
        params: { path: { account_id: id } },
      } as never),
    listTransactions: (id: string, query?: Record<string, unknown>) =>
      api.GET("/shares/accounts/{account_id}/transactions" as never, {
        params: { path: { account_id: id }, query },
      } as never),
    purchase: (id: string, body: Record<string, unknown>) =>
      api.POST("/shares/accounts/{account_id}/purchase" as never, {
        params: { path: { account_id: id } },
        body,
      } as never),
    redeem: (id: string, body: Record<string, unknown>) =>
      api.POST("/shares/accounts/{account_id}/redeem" as never, {
        params: { path: { account_id: id } },
        body,
      } as never),
  } as const;
}
