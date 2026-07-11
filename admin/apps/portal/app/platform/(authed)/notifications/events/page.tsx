import type { NotificationEventAdminOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { NotificationsProviderBanner } from "@/components/NotificationsProviderBanner";
import { EventsTable } from "./_components/EventsTable";

export const metadata = { title: "Notification events" };

export default async function NotificationEventsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "settings.read");

  const one = (k: string): string | undefined =>
    typeof sp[k] === "string" ? (sp[k] as string) : undefined;

  const page = Number(one("page") ?? "1");
  const pageSize = Number(one("pageSize") ?? "25");
  const query: Record<string, unknown> = {
    limit: pageSize,
    offset: (page - 1) * pageSize,
  };
  const status = one("f_status");
  if (status) query["status"] = status;
  const eventCode = one("f_event_code");
  if (eventCode) query["event_code"] = eventCode;

  // searchEvents is typed Promise<never> (as-never paths); cast to the
  // real { data, error } shape.
  const { data } = await (resources.notifications.searchEvents(query) as Promise<{
    data?: NotificationEventAdminOut[];
    error?: unknown;
  }>);
  const rows = data ?? [];

  // The API returns a bare list (no total). A full page means "at least one
  // more" so the pager's next button stays enabled.
  const totalRows =
    (page - 1) * pageSize + rows.length + (rows.length === pageSize ? 1 : 0);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Notification events</h1>
      <NotificationsProviderBanner />
      <EventsTable rows={rows} totalRows={totalRows} />
    </div>
  );
}
