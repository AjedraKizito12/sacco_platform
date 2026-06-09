import type { FetchClient } from "../client";

export function platformAuth(api: FetchClient) {
  return {
    login: (body: { email: string; password: string }) =>
      api.POST("/platform/auth/token" as never, { body } as never),
    refresh: (body: { refresh_token: string }) =>
      api.POST("/platform/auth/refresh" as never, { body } as never),
    logout: () => api.POST("/platform/auth/logout" as never),
    me: () => api.GET("/platform/auth/me" as never),
    passwordResetRequest: (body: { email: string }) =>
      api.POST("/platform/auth/password-reset/request" as never, { body } as never),
    passwordResetConfirm: (body: { token: string; new_password: string }) =>
      api.POST("/platform/auth/password-reset/confirm" as never, { body } as never),
  } as const;
}
