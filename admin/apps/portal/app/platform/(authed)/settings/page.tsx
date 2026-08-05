import Link from "next/link";
import { Card } from "@sacco/ui";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";

export const metadata = { title: "Settings" };

function SettingCard({ href, title, desc }: { href: string; title: string; desc: string }) {
  return (
    <Link href={href} className="block">
      <Card className="flex flex-col gap-1 p-5 transition-colors hover:bg-[var(--surface-hover)]">
        <span className="text-[var(--text-h5)] font-semibold text-[var(--text-primary)]">
          {title}
        </span>
        <span className="text-[13px] text-[var(--text-secondary)]">{desc}</span>
      </Card>
    </Link>
  );
}

export default async function SettingsPage() {
  const { user } = await getPlatformPageContext();
  requirePlatformPermission(user, "settings.read");
  const canSecurity = userHasPermission(user, "platform.security.jwt_keys.read");

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Settings</h1>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <SettingCard
          href="/platform/settings/billing"
          title="Billing"
          desc="Invoice numbering, plans, and grace period."
        />
        <SettingCard
          href="/platform/settings/notifications"
          title="Notifications"
          desc="Email and SMS provider configuration."
        />
        <SettingCard
          href="/platform/settings/rate-limits"
          title="Rate limits"
          desc="Per-window request budgets and per-plan overrides."
        />
        {canSecurity ? (
          <SettingCard
            href="/platform/settings/security"
            title="Security"
            desc="JWT signing keys and security policy."
          />
        ) : null}
      </div>
    </div>
  );
}
