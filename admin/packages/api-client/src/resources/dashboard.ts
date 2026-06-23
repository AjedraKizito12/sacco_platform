import type { FetchClient } from "../client";

export function dashboard(api: FetchClient) {
  return {
    // Tenant-scoped aggregate for the operator dashboard. X-Tenant-Slug is
    // injected by the client's tenant context.
    tenantStats: () => api.GET("/dashboard/stats" as never),
  } as const;
}
