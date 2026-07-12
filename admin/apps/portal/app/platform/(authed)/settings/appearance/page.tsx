import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { AppearanceSection } from "@/components/theme/AppearanceSection";

export const metadata = { title: "Appearance" };

export default async function PlatformAppearanceSettingsPage() {
  const { user } = await getPlatformPageContext();
  requirePlatformPermission(user, "settings.read");

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Appearance</h1>
      <AppearanceSection />
    </div>
  );
}
