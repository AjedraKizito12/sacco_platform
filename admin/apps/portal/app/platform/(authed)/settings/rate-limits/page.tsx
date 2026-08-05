import { Card } from "@sacco/ui";
import type { RateLimitConfigOut, TenantOut } from "@sacco/schemas";
import { flattenRateLimitOverrides } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { PolicyTable } from "./_components/PolicyTable";
import { OverridesTable } from "./_components/OverridesTable";
import { TenantLivePanel } from "./_components/TenantLivePanel";

export const metadata = { title: "Rate limits" };

export default async function RateLimitsSettingsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "settings.read");

  // getConfig / tenants.list are typed Promise<never> (the resources use
  // `as never` openapi-fetch paths); cast to the real { data, error } shape.
  const [configRes, tenantsRes] = await Promise.all([
    resources.rateLimits.getConfig() as Promise<{
      data?: RateLimitConfigOut;
      error?: unknown;
    }>,
    resources.tenants.list() as Promise<{ data?: TenantOut[]; error?: unknown }>,
  ]);

  const config = configRes.data;
  if (!config) {
    throw new Error(
      `Failed to load rate-limit config: ${JSON.stringify(configRes.error)}`,
    );
  }

  const overrideRows = flattenRateLimitOverrides(config.plan_overrides);
  const tenants = (tenantsRes.data ?? []).map((t) => ({ id: t.id, name: t.name }));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-[var(--text-h3)] font-semibold">Rate limits</h1>
        <p className="text-[13px] text-[var(--text-secondary)]">
          Per-window request budgets enforced by the API. Limits are read-only
          here; per-plan overrides are configured on the subscription plan.
        </p>
      </div>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Default policies</h2>
        <PolicyTable policies={config.defaults} />
      </Card>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Plan overrides</h2>
        <OverridesTable rows={overrideRows} />
      </Card>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">
          Live consumption
        </h2>
        <p className="text-[13px] text-[var(--text-secondary)]">
          Worst-case remaining tokens across a tenant&apos;s active users right
          now — the user closest to being throttled for each policy.
        </p>
        <TenantLivePanel tenants={tenants} />
      </Card>
    </div>
  );
}
