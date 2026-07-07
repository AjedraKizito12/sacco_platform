import type { FetchClient } from "../client";

export function kyc(api: FetchClient) {
  return {
    getSaccoRequirements: () =>
      api.GET("/platform/kyc/sacco-requirements" as never),
    putSaccoRequirements: (body: { required: Record<string, boolean> }) =>
      api.PUT("/platform/kyc/sacco-requirements" as never, { body } as never),
    getTenantKyc: (tenantId: string) =>
      api.GET("/platform/tenants/{tenant_id}/kyc" as never, {
        params: { path: { tenant_id: tenantId } },
      } as never),
    verifyTenant: (tenantId: string) =>
      api.POST("/platform/tenants/{tenant_id}/kyc/verify" as never, {
        params: { path: { tenant_id: tenantId } },
      } as never),
    unverifyTenant: (tenantId: string) =>
      api.POST("/platform/tenants/{tenant_id}/kyc/unverify" as never, {
        params: { path: { tenant_id: tenantId } },
      } as never),
  } as const;
}
