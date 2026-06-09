import type { FetchClient } from "../client";

export function impersonations(api: FetchClient) {
  return {
    request: (body: { tenant_id: string; reason: string }) =>
      api.POST("/platform/impersonations" as never, { body } as never),
    listActive: () =>
      api.GET("/platform/impersonations/active" as never),
    listAll: (query?: Record<string, unknown>) =>
      api.GET("/platform/impersonations/all" as never, { params: { query } } as never),
    get: (id: string) =>
      api.GET("/platform/impersonations/{impersonation_id}" as never, {
        params: { path: { impersonation_id: id } },
      } as never),
    end: (id: string) =>
      api.DELETE("/platform/impersonations/{impersonation_id}" as never, {
        params: { path: { impersonation_id: id } },
      } as never),
    mintTenantToken: (id: string) =>
      api.POST("/platform/impersonations/{impersonation_id}/mint-tenant-token" as never, {
        params: { path: { impersonation_id: id } },
      } as never),
    revoke: (id: string) =>
      api.POST("/platform/impersonations/{impersonation_id}/revoke" as never, {
        params: { path: { impersonation_id: id } },
      } as never),
  } as const;
}
