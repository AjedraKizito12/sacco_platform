import type { FetchClient } from "../client";

export function admin(api: FetchClient) {
  return {
    dashboardStats: () =>
      api.GET("/platform/admin/dashboard-stats" as never),
    listUsers: (query?: Record<string, unknown>) =>
      api.GET("/platform/users" as never, { params: { query } } as never),
    getUser: (id: string) =>
      api.GET("/platform/users/{user_id}" as never, {
        params: { path: { user_id: id } },
      } as never),
    createUser: (body: Record<string, unknown>) =>
      api.POST("/platform/users" as never, { body } as never),
    patchUser: (id: string, body: Record<string, unknown>) =>
      api.PATCH("/platform/users/{user_id}" as never, {
        params: { path: { user_id: id } },
        body,
      } as never),
  } as const;
}
