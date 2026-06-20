import { Card } from "@sacco/ui";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";

export const metadata = { title: "Notification settings" };

export default async function NotificationSettingsPage() {
  const { user } = await getPlatformPageContext();
  requirePlatformPermission(user, "settings.read");

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Notification settings</h1>
      <Card className="p-6 text-[var(--text-secondary)]">
        Notifications coming soon — email and SMS providers wire up in Phase 3.
      </Card>
    </div>
  );
}
