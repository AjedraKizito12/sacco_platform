import type { FetchClient } from "../client";

export function members(api: FetchClient) {
  return {
    list: (query?: Record<string, unknown>) =>
      api.GET("/members" as never, { params: { query } } as never),
    get: (id: string) =>
      api.GET("/members/{member_id}" as never, {
        params: { path: { member_id: id } },
      } as never),
    create: (body: Record<string, unknown>) =>
      api.POST("/members" as never, { body } as never),
    changeStatus: (id: string, body: Record<string, unknown>) =>
      api.POST("/members/{member_id}/status-change" as never, {
        params: { path: { member_id: id } },
        body,
      } as never),
  } as const;
}
