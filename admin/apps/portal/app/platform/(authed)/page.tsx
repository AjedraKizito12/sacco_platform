import type { ReactNode } from "react";
import {
  Card,
  Count,
  FormattedDateTime,
  KpiCard,
  Money,
  StatusBadge,
} from "@sacco/ui";
import type { DashboardStatsOut } from "@sacco/schemas";
import { getPlatformPageContext } from "@/auth/server-page-context";

const DASH = "—";

function sumValues(d: Record<string, number>): number {
  return Object.values(d).reduce((a, b) => a + b, 0);
}

function MoneyList({ amounts }: { amounts: Record<string, string> }): ReactNode {
  const entries = Object.entries(amounts);
  if (entries.length === 0) return <>{DASH}</>;
  return (
    <span className="flex flex-col">
      {entries.map(([currency, amount], i) =>
        i === 0 ? (
          <Money key={currency} amount={amount} currency={currency} size="large" />
        ) : (
          <Money
            key={currency}
            amount={amount}
            currency={currency}
            className="text-[13px] text-[var(--text-secondary)]"
          />
        ),
      )}
    </span>
  );
}

export default async function PlatformDashboard() {
  const { resources } = await getPlatformPageContext();

  // dashboard-stats is admin-gated at the API. The dashboard is the landing
  // page for every authenticated platform user, so a support/finance user
  // gets no data here — fall back to placeholders rather than failing.
  const { data } = await (
    resources.admin.dashboardStats() as Promise<{
      data?: DashboardStatsOut;
      error?: unknown;
    }>
  );

  return (
    <div className="flex flex-col gap-6">
      <Card className="p-6">
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
          Platform dashboard
        </h1>
        <p className="text-[var(--text-secondary)]">
          {data ? (
            <>
              Last refreshed{" "}
              <FormattedDateTime value={data.last_updated} />
            </>
          ) : (
            "Platform-wide metrics are available to admins."
          )}
        </p>
      </Card>

      <div className="grid grid-cols-3 gap-4">
        <KpiCard
          label="Total tenants"
          value={data ? <Count value={sumValues(data.tenants)} /> : DASH}
        />
        <KpiCard
          label="Monthly recurring revenue"
          value={data ? <MoneyList amounts={data.mrr} /> : DASH}
        />
        <KpiCard
          label="Outstanding invoices"
          value={
            data ? <Count value={sumValues(data.invoices_outstanding)} /> : DASH
          }
        />
      </div>

      <Card className="p-6">
        <h2 className="mb-3 text-[18px] font-semibold">Sample status row</h2>
        <div className="flex flex-wrap gap-2">
          <StatusBadge entity="tenant" status="active" />
          <StatusBadge entity="tenant" status="provisioning" />
          <StatusBadge entity="invoice" status="overdue" />
          <StatusBadge entity="approval_request" status="pending" />
        </div>
      </Card>
    </div>
  );
}
