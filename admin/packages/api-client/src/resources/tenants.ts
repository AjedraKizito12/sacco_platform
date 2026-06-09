import type { FetchClient } from "../client";

export function tenants(api: FetchClient) {
  return {
    list: (query?: { status?: string }) =>
      api.GET("/platform/tenants" as never, { params: { query } } as never),
    get: (id: string) =>
      api.GET("/platform/tenants/{tenant_id}" as never, {
        params: { path: { tenant_id: id } },
      } as never),
    create: (body: { slug: string; name: string; admin_email?: string }) =>
      api.POST("/platform/tenants" as never, { body } as never),
    retryProvisioning: (id: string) =>
      api.POST("/platform/tenants/{tenant_id}/retry-provisioning" as never, {
        params: { path: { tenant_id: id } },
      } as never),
    // Phase 1.7 lifecycle endpoints
    patch: (id: string, body: { name: string }) =>
      api.PATCH("/platform/tenants/{tenant_id}" as never, {
        params: { path: { tenant_id: id } },
        body,
      } as never),
    suspend: (id: string, body: { reason: string }) =>
      api.POST("/platform/tenants/{tenant_id}/suspend" as never, {
        params: { path: { tenant_id: id } },
        body,
      } as never),
    reactivate: (id: string) =>
      api.POST("/platform/tenants/{tenant_id}/reactivate" as never, {
        params: { path: { tenant_id: id } },
      } as never),
    assignPlan: (id: string, body: { plan_id: string; start_date?: string }) =>
      api.POST("/platform/tenants/{tenant_id}/assign-plan" as never, {
        params: { path: { tenant_id: id } },
        body,
      } as never),
    // Tenant-user admin (Phase 1.7 #7)
    listUsers: (id: string) =>
      api.GET("/platform/tenants/{tenant_id}/users" as never, {
        params: { path: { tenant_id: id } },
      } as never),
    getUser: (id: string, userId: string) =>
      api.GET("/platform/tenants/{tenant_id}/users/{user_id}" as never, {
        params: { path: { tenant_id: id, user_id: userId } },
      } as never),
    createUser: (
      id: string,
      body: { email: string; full_name: string; is_admin?: boolean },
    ) =>
      api.POST("/platform/tenants/{tenant_id}/users" as never, {
        params: { path: { tenant_id: id } },
        body,
      } as never),
    patchUser: (
      id: string,
      userId: string,
      body: { full_name?: string; is_active?: boolean; is_admin?: boolean },
    ) =>
      api.PATCH("/platform/tenants/{tenant_id}/users/{user_id}" as never, {
        params: { path: { tenant_id: id, user_id: userId } },
        body,
      } as never),
    resetUserPassword: (id: string, userId: string) =>
      api.POST(
        "/platform/tenants/{tenant_id}/users/{user_id}/password-reset" as never,
        { params: { path: { tenant_id: id, user_id: userId } } } as never,
      ),
  } as const;
}
