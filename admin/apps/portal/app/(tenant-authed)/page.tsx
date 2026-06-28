import { AlertTriangle, Banknote, PiggyBank, Users } from "lucide-react";
import { Count, FormattedDateTime, Money } from "@sacco/ui";
import type { TenantDashboardStatsOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { DashboardHero } from "@/components/dashboard/DashboardHero";
import { StatTile, StatTileGrid } from "@/components/dashboard/StatTile";

const DASH = "—";

export default async function TenantDashboard() {
  const { resources } = await getTenantPageContext();

  const { data } = await (
    resources.dashboard.tenantStats() as Promise<{
      data?: TenantDashboardStatsOut;
      error?: unknown;
    }>
  );

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-[length:var(--text-h4)] font-semibold">Dashboard</h1>
        <p className="mt-1 text-[13px] text-[var(--text-tertiary)]">
          {data ? (
            <>
              Last refreshed <FormattedDateTime value={data.last_updated} />
            </>
          ) : (
            "Couldn't load dashboard metrics. Please try again."
          )}
        </p>
      </div>

      <DashboardHero label="Total savings" icon={<PiggyBank size={18} />}>
        {data ? <Money amount={data.total_savings} /> : DASH}
      </DashboardHero>

      <StatTileGrid>
        <StatTile
          label="Total members"
          icon={<Users size={18} />}
          href="/members"
          hint="Across the SACCO"
        >
          {data ? <Count value={data.total_members} /> : DASH}
        </StatTile>
        <StatTile
          label="Outstanding loans"
          icon={<Banknote size={18} />}
          href="/credit"
          hint="Principal balance"
        >
          {data ? <Money amount={data.loans_outstanding_principal} /> : DASH}
        </StatTile>
        <StatTile
          label="Members in arrears"
          icon={<AlertTriangle size={18} />}
          hint={
            data && data.members_in_arrears === 0
              ? "None overdue"
              : "Need follow-up"
          }
        >
          {data ? <Count value={data.members_in_arrears} /> : DASH}
        </StatTile>
      </StatTileGrid>
    </div>
  );
}
