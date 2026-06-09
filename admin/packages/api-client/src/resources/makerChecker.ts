import type { FetchClient } from "../client";

export function makerChecker(api: FetchClient) {
  return {
    // Platform-scoped approvals
    listPlatform: (query?: Record<string, unknown>) =>
      api.GET("/platform/approvals" as never, { params: { query } } as never),
    submitPlatform: (body: Record<string, unknown>) =>
      api.POST("/platform/approvals" as never, { body } as never),
    getPlatform: (id: string) =>
      api.GET("/platform/approvals/{request_id}" as never, {
        params: { path: { request_id: id } },
      } as never),
    approvePlatform: (id: string, body: Record<string, unknown>) =>
      api.POST("/platform/approvals/{request_id}/approve" as never, {
        params: { path: { request_id: id } },
        body,
      } as never),
    rejectPlatform: (id: string, body: Record<string, unknown>) =>
      api.POST("/platform/approvals/{request_id}/reject" as never, {
        params: { path: { request_id: id } },
        body,
      } as never),
    cancelPlatform: (id: string, body: Record<string, unknown>) =>
      api.POST("/platform/approvals/{request_id}/cancel" as never, {
        params: { path: { request_id: id } },
        body,
      } as never),

    // Tenant-scoped approvals
    listTenant: (query?: Record<string, unknown>) =>
      api.GET("/approvals" as never, { params: { query } } as never),
    submitTenant: (body: Record<string, unknown>) =>
      api.POST("/approvals" as never, { body } as never),
    getTenant: (id: string) =>
      api.GET("/approvals/{request_id}" as never, {
        params: { path: { request_id: id } },
      } as never),
    approveTenant: (id: string, body: Record<string, unknown>) =>
      api.POST("/approvals/{request_id}/approve" as never, {
        params: { path: { request_id: id } },
        body,
      } as never),
    rejectTenant: (id: string, body: Record<string, unknown>) =>
      api.POST("/approvals/{request_id}/reject" as never, {
        params: { path: { request_id: id } },
        body,
      } as never),
    cancelTenant: (id: string, body: Record<string, unknown>) =>
      api.POST("/approvals/{request_id}/cancel" as never, {
        params: { path: { request_id: id } },
        body,
      } as never),
  } as const;
}
