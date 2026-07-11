import type { NotificationPreferenceOut } from "@sacco/schemas";
import { getMemberPageContext } from "@/auth/server-page-context";
import { NotificationPreferencesForm } from "@/components/notifications/NotificationPreferencesForm";

export const metadata = { title: "Notification preferences" };

export default async function MemberNotificationPreferencesPage() {
  const { resources } = await getMemberPageContext();

  // getPreferences is typed Promise<never> (as-never paths); cast to the
  // real { data, error } shape.
  const { data, error } = await (resources.notifications.getPreferences(
    "member",
  ) as Promise<{ data?: NotificationPreferenceOut[]; error?: unknown }>);
  if (!data) {
    throw new Error(
      `Failed to load notification preferences: ${JSON.stringify(error)}`,
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">
        Notification preferences
      </h1>
      <NotificationPreferencesForm audience="member" initial={data} />
    </div>
  );
}
