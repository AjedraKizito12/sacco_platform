import type { FetchClient } from "../client";

export function memberAuth(api: FetchClient) {
  return {
    login: (body: Record<string, unknown>) =>
      api.POST("/member/auth/token" as never, { body } as never),
    refresh: (body: Record<string, unknown>) =>
      api.POST("/member/auth/refresh" as never, { body } as never),
    logout: () => api.POST("/member/auth/logout" as never, {} as never),
    me: () => api.GET("/member/auth/me" as never, {} as never),
    resetRequest: (body: Record<string, unknown>) =>
      api.POST("/member/auth/password-reset/request" as never, {
        body,
      } as never),
    resetConfirm: (body: Record<string, unknown>) =>
      api.POST("/member/auth/password-reset/confirm" as never, {
        body,
      } as never),
  } as const;
}
