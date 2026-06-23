import {
  Card,
  Count,
  FormattedDateTime,
  KpiCard,
  Money,
  StatusBadge,
} from "@sacco/ui";
import type { TenantDashboardStatsOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";

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
      <Card className="p-6">
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
          Tenant dashboard
        </h1>
        <p className="text-[var(--text-secondary)]">
          {data ? (
            <>
              Last refreshed{" "}
              <FormattedDateTime value={data.last_updated} />
            </>
          ) : (
            "Couldn't load dashboard metrics. Please try again."
          )}
        </p>
      </Card>

      <div className="grid grid-cols-4 gap-4">
        <KpiCard
          label="Total members"
          value={data ? <Count value={data.total_members} /> : DASH}
        />
        <KpiCard
          label="Total savings"
          value={
            data ? <Money amount={data.total_savings} size="large" /> : DASH
          }
        />
        <KpiCard
          label="Outstanding loans"
          value={
            data ? (
              <Money amount={data.loans_outstanding_principal} size="large" />
            ) : (
              DASH
            )
          }
        />
        <KpiCard
          label="Members in arrears"
          value={data ? <Count value={data.members_in_arrears} /> : DASH}
        />
      </div>

      <Card className="p-6">
        <h2 className="mb-3 text-[18px] font-semibold">Sample status row</h2>
        <div className="flex flex-wrap gap-2">
          <StatusBadge entity="member" status="active" />
          <StatusBadge entity="member" status="dormant" />
          <StatusBadge entity="loan" status="in_arrears" />
          <StatusBadge entity="savings_account" status="frozen" />
        </div>
      </Card>
    </div>
  );
}
