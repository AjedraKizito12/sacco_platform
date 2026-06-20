import { Card } from "@sacco/ui";
import type { JwtKeyOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { JwtKeysTable } from "./_components/JwtKeysTable";

export const metadata = { title: "Security settings" };

export default async function SecuritySettingsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.security.jwt_keys.read");

  const { data } = await (
    resources.keys.listJwtKeys() as Promise<{ data?: JwtKeyOut[]; error?: unknown }>
  );

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Security</h1>
      <JwtKeysTable rows={data ?? []} />
      <Card className="p-6 text-[13px] text-[var(--text-secondary)]">
        Signing keys are rotated automatically by a scheduled job. Session TTL and password
        policy are managed via environment configuration.
      </Card>
    </div>
  );
}
