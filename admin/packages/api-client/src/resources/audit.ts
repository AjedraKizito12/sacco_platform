import type { FetchClient } from "../client";

export function audit(api: FetchClient) {
  return {
    listPlatform: (query?: Record<string, unknown>) =>
      api.GET("/platform/audit-log" as never, { params: { query } } as never),
    listTenant: (tenantId: string, query?: Record<string, unknown>) =>
      api.GET("/platform/tenants/{tenant_id}/audit-log" as never, {
        params: { path: { tenant_id: tenantId }, query },
      } as never),
    listOperator: (query?: Record<string, unknown>) =>
      api.GET("/audit-log" as never, { params: { query } } as never),
  } as const;
}
