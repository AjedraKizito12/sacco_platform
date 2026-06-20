import type { ReactNode } from "react";
import { Card, Count, Money, RelativeTime } from "@sacco/ui";
import type { DashboardStatsOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { StatCard } from "./_components/StatCard";
import { StatusBreakdown } from "./_components/StatusBreakdown";
import { RefreshButton } from "./_components/RefreshButton";

export const metadata = { title: "Operations" };

function sumValues(d: Record<string, number>): number {
  return Object.values(d).reduce((a, b) => a + b, 0);
}

function MoneyList({ amounts }: { amounts: Record<string, string> }): ReactNode {
  const entries = Object.entries(amounts);
  if (entries.length === 0) return <>—</>;
  return (
    <span className="flex flex-col">
      {entries.map(([currency, amount], i) => (
        <Money
          key={currency}
          amount={amount}
          currency={currency}
          className={i === 0 ? "" : "text-[13px] text-[var(--text-secondary)]"}
        />
      ))}
    </span>
  );
}

export default async function OperationsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "operations.read");

  const { data } = await (
    resources.admin.dashboardStats() as Promise<{
      data?: DashboardStatsOut;
      error?: unknown;
    }>
  );

  if (!data) {
    return (
      <div className="flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <h1 className="text-[var(--text-h3)] font-semibold">Operations</h1>
          <RefreshButton />
        </div>
        <Card className="p-6 text-[var(--text-secondary)]">
          Couldn&apos;t load operations stats. Please try again.
        </Card>
      </div>
    );
  }

  const outstandingEntries = Object.entries(data.invoices_outstanding);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Operations</h1>
        <div className="flex items-center gap-3">
          <span className="text-[13px] text-[var(--text-tertiary)]">
            Last updated <RelativeTime value={data.last_updated} />
          </span>
          <RefreshButton />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Tenants"
          value={<Count value={sumValues(data.tenants)} />}
          sub={
            <>
              <Count value={data.tenants["active"] ?? 0} /> active
            </>
          }
        />
        <StatCard label="MRR" value={<MoneyList amounts={data.mrr} />} />
        <StatCard
          label="Pending approvals"
          value={<Count value={data.approvals_pending} />}
          href="/platform/approvals?status=pending"
        />
        <StatCard
          label="Active impersonations"
          value={<Count value={data.active_impersonations} />}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <StatusBreakdown title="Tenants by status" entity="tenant" counts={data.tenants} />
        <StatusBreakdown
          title="Subscriptions by status"
          entity="subscription"
          counts={data.subscriptions}
        />
      </div>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Outstanding invoices</h2>
        {outstandingEntries.length === 0 ? (
          <p className="text-[var(--text-tertiary)]">No outstanding invoices</p>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {outstandingEntries.map(([status, count]) => (
                <span key={status} className="text-[var(--text-secondary)]">
                  {status} <Count value={count} className="text-[var(--text-primary)]" />
                </span>
              ))}
            </div>
            <MoneyList amounts={data.invoices_amount_outstanding} />
          </div>
        )}
        <a
          href="/platform/billing/invoices"
          className="self-start text-[13px] text-[var(--text-link)] hover:underline"
        >
          View invoices
        </a>
      </Card>
    </div>
  );
}
