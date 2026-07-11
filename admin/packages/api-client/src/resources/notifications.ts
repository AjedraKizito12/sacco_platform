import type { FetchClient } from "../client";

export type NotificationAudience = "platform" | "tenant" | "member";

const SELF_PREFIX = {
  platform: "/platform/notifications/me",
  tenant: "/notifications/me",
  member: "/member/notifications/me",
} as const satisfies Record<NotificationAudience, string>;

export function notifications(api: FetchClient) {
  return {
    feed: (audience: NotificationAudience, query?: Record<string, unknown>) =>
      api.GET(SELF_PREFIX[audience] as never, { params: { query } } as never),
    markRead: (audience: NotificationAudience, eventId: string) =>
      api.POST(`${SELF_PREFIX[audience]}/{event_id}/read` as never, {
        params: { path: { event_id: eventId } },
      } as never),
    getPreferences: (audience: NotificationAudience) =>
      api.GET(`${SELF_PREFIX[audience]}/preferences` as never),
    putPreferences: (audience: NotificationAudience, body: unknown[]) =>
      api.PUT(`${SELF_PREFIX[audience]}/preferences` as never, {
        body,
      } as never),
    listTemplates: () => api.GET("/platform/notifications/templates" as never),
    createTemplate: (body: Record<string, unknown>) =>
      api.POST("/platform/notifications/templates" as never, {
        body,
      } as never),
    patchTemplate: (templateId: string, body: Record<string, unknown>) =>
      api.PATCH("/platform/notifications/templates/{template_id}" as never, {
        params: { path: { template_id: templateId } },
        body,
      } as never),
    searchEvents: (query?: Record<string, unknown>) =>
      api.GET("/platform/notifications/events" as never, {
        params: { query },
      } as never),
    resendEvent: (eventId: string) =>
      api.POST("/platform/notifications/events/{event_id}/resend" as never, {
        params: { path: { event_id: eventId } },
      } as never),
  } as const;
}
