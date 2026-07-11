"use client";

import { queryKeys, useTypedMutation, useTypedQuery } from "@sacco/api-client";
import type { NotificationFeedItemOut } from "@sacco/schemas";
import { NotificationBell } from "@sacco/ui";
import { useRouter } from "next/navigation";
import { useAuth } from "@/auth/use-auth";

const PREFERENCES_ROUTE = {
  platform: "/platform/settings/notifications",
  tenant: "/notifications/preferences",
  member: "/member/notifications/preferences",
} as const;

const POLL_INTERVAL_MS = 60_000;

interface AppShellNotificationBellProps {
  variant: "platform" | "tenant" | "member";
}

/**
 * The one sanctioned client-fetch widget (contract M carve-out): the bell
 * lives in the shell, not a page, so it polls its audience's feed directly.
 */
export function AppShellNotificationBell({
  variant,
}: AppShellNotificationBellProps) {
  const { resources } = useAuth();
  const router = useRouter();

  const feedQuery = useTypedQuery<NotificationFeedItemOut[]>(
    queryKeys.notifications.feed(variant),
    async () => {
      const res = await (
        resources.notifications.feed(variant, { limit: 20 }) as Promise<{
          data?: NotificationFeedItemOut[];
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data ?? [];
    },
    { refetchInterval: POLL_INTERVAL_MS },
  );

  const markRead = useTypedMutation(
    (eventId: string) =>
      resources.notifications.markRead(variant, eventId) as Promise<unknown>,
    { invalidates: [queryKeys.notifications.feed(variant)] },
  );

  const feedItems = feedQuery.data ?? [];
  const unreadCount = feedItems.filter((item) => item.read_at === null).length;

  return (
    <NotificationBell
      items={feedItems.map((item) => ({
        id: item.id,
        title: item.title,
        body: item.body,
        createdAt: item.created_at,
        readAt: item.read_at,
      }))}
      unreadCount={unreadCount}
      loading={feedQuery.isLoading}
      onItemClick={(id) => {
        const item = feedItems.find((row) => row.id === id);
        if (item && item.read_at === null) markRead.mutate(id);
      }}
      onOpenPreferences={() => router.push(PREFERENCES_ROUTE[variant])}
    />
  );
}
