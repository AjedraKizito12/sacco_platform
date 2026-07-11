import type { NotificationTemplateOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { NotificationsProviderBanner } from "@/components/NotificationsProviderBanner";
import { TemplatesTable } from "./_components/TemplatesTable";

export const metadata = { title: "Notification templates" };

export default async function NotificationTemplatesPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "settings.read");

  // listTemplates is typed Promise<never> (as-never paths); cast to the
  // real { data, error } shape.
  const { data, error } = await (resources.notifications.listTemplates() as Promise<{
    data?: NotificationTemplateOut[];
    error?: unknown;
  }>);
  if (!data) {
    throw new Error(
      `Failed to load notification templates: ${JSON.stringify(error)}`,
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">
        Notification templates
      </h1>
      <NotificationsProviderBanner />
      <TemplatesTable rows={data} />
    </div>
  );
}
