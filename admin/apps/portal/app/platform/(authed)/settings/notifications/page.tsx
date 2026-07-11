import type { NotificationPreferenceOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { NotificationsProviderBanner } from "@/components/NotificationsProviderBanner";
import { NotificationPreferencesForm } from "@/components/notifications/NotificationPreferencesForm";

export const metadata = { title: "Notification settings" };

export default async function NotificationSettingsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "settings.read");

  // getPreferences is typed Promise<never> (as-never paths); cast to the
  // real { data, error } shape.
  const { data, error } = await (resources.notifications.getPreferences(
    "platform",
  ) as Promise<{ data?: NotificationPreferenceOut[]; error?: unknown }>);
  if (!data) {
    throw new Error(
      `Failed to load notification preferences: ${JSON.stringify(error)}`,
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Notification settings</h1>
      <NotificationsProviderBanner />
      <NotificationPreferencesForm audience="platform" initial={data} />
    </div>
  );
}
