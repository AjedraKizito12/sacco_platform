import { Card, FormattedDate, KpiCard, Money, StatusBadge } from "@sacco/ui";

export default function TenantDashboard() {
  return (
    <div className="flex flex-col gap-6">
      <Card className="p-6">
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
          Tenant dashboard
        </h1>
        <p className="text-[var(--text-secondary)]">
          Sub-plan 35 wires the real KPIs, charts, recent activity.
        </p>
      </Card>

      <div className="grid grid-cols-4 gap-4">
        <KpiCard label="Total members" value="—" />
        <KpiCard
          label="Total savings"
          value={<Money amount="0" size="large" />}
        />
        <KpiCard
          label="Outstanding loans"
          value={<Money amount="0" size="large" />}
        />
        <KpiCard label="Members in arrears" value="—" />
      </div>

      <Card className="p-6">
        <h2 className="mb-3 text-[18px] font-semibold">Sample status row</h2>
        <div className="flex flex-wrap gap-2">
          <StatusBadge entity="member" status="active" />
          <StatusBadge entity="member" status="dormant" />
          <StatusBadge entity="loan" status="in_arrears" />
          <StatusBadge entity="savings_account" status="frozen" />
        </div>
        <p className="mt-3 text-[12px] text-[var(--text-tertiary)]">
          As of <FormattedDate value={new Date().toISOString()} />
        </p>
      </Card>
    </div>
  );
}
