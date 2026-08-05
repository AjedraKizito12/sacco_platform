import type { FetchClient } from "../client";

// Read-only rate-limit config + per-tenant live view (admin).
// Mirrors app/platform_/rate_limits/api.py.
export function rateLimits(api: FetchClient) {
  return {
    getConfig: () => api.GET("/platform/rate-limits" as never),
    getTenantLive: (tenantId: string) =>
      api.GET("/platform/rate-limits/tenants/{tenant_id}/live" as never, {
        params: { path: { tenant_id: tenantId } },
      } as never),
  } as const;
}
