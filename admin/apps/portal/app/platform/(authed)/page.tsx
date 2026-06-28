import type { ReactNode } from "react";
import { Building2, FileText, Wallet } from "lucide-react";
import { Count, FormattedDateTime, Money } from "@sacco/ui";
import type { DashboardStatsOut } from "@sacco/schemas";
import { getPlatformPageContext } from "@/auth/server-page-context";
import { DashboardHero } from "@/components/dashboard/DashboardHero";
import { StatTile, StatTileGrid } from "@/components/dashboard/StatTile";

const DASH = "—";

function sumValues(d: Record<string, number>): number {
  return Object.values(d).reduce((a, b) => a + b, 0);
}

/** MRR can span currencies — the first is the headline, the rest list below. */
function HeroMrr({ mrr }: { mrr: Record<string, string> }): ReactNode {
  const entries = Object.entries(mrr);
  const first = entries[0];
  // No active/trialing subscriptions → MRR is genuinely zero (billing is
  // UGX-only in v1). A real zero reads better than a bare dash in the hero.
  if (!first) return <Money amount="0" currency="UGX" />;
  return (
    <span className="flex flex-col gap-1">
      <Money amount={first[1]} currency={first[0]} />
      {entries.slice(1).map(([currency, amount]) => (
        <Money
          key={currency}
          amount={amount}
          currency={currency}
          className="text-[14px] font-normal text-white/70"
        />
      ))}
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
      <div>
        <h1 className="text-[length:var(--text-h4)] font-semibold">
          Platform dashboard
        </h1>
        <p className="mt-1 text-[13px] text-[var(--text-tertiary)]">
          {data ? (
            <>
              Last refreshed <FormattedDateTime value={data.last_updated} />
            </>
          ) : (
            "Platform-wide metrics are available to admins."
          )}
        </p>
      </div>

      <DashboardHero label="Monthly recurring revenue" icon={<Wallet size={18} />}>
        {data ? <HeroMrr mrr={data.mrr} /> : DASH}
      </DashboardHero>

      <StatTileGrid>
        <StatTile
          label="Total tenants"
          icon={<Building2 size={18} />}
          href="/platform/tenants"
          hint="All SACCOs"
        >
          {data ? <Count value={sumValues(data.tenants)} /> : DASH}
        </StatTile>
        <StatTile
          label="Outstanding invoices"
          icon={<FileText size={18} />}
          href="/platform/billing/invoices"
          hint="Awaiting payment"
        >
          {data ? <Count value={sumValues(data.invoices_outstanding)} /> : DASH}
        </StatTile>
      </StatTileGrid>
    </div>
  );
}
