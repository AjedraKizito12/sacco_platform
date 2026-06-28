import type { ReactNode } from "react";
import {
  AlertTriangle,
  Building2,
  CreditCard,
  FileText,
  Receipt,
  ShieldAlert,
  UserCog,
  Wallet,
} from "lucide-react";
import { Count, FormattedDateTime, Money } from "@sacco/ui";
import type { DashboardStatsOut } from "@sacco/schemas";
import { getPlatformPageContext } from "@/auth/server-page-context";
import { DashboardHero } from "@/components/dashboard/DashboardHero";
import { NeedsAttention } from "@/components/dashboard/NeedsAttention";
import { QuickLinks } from "@/components/dashboard/QuickLinks";
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

  const activeSubs = data
    ? (data.subscriptions["active"] ?? 0) + (data.subscriptions["trialing"] ?? 0)
    : 0;
  const pastDueSubs = data?.subscriptions["past_due"] ?? 0;
  const suspendedTenants = data?.tenants["suspended"] ?? 0;
  const overdueInvoices = data?.invoices_outstanding["overdue"] ?? 0;

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
          label="Active subscriptions"
          icon={<CreditCard size={18} />}
          href="/platform/billing/subscriptions"
          hint="Active + trialing"
        >
          {data ? <Count value={activeSubs} /> : DASH}
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

      {data ? (
        <NeedsAttention
          items={[
            {
              icon: <FileText size={16} />,
              label: "Platform approvals pending",
              href: "/platform/approvals",
              count: data.approvals_pending,
              value: <Count value={data.approvals_pending} />,
              tone: "info",
            },
            {
              icon: <ShieldAlert size={16} />,
              label: "Active impersonation sessions",
              href: "/platform/operations",
              count: data.active_impersonations,
              value: <Count value={data.active_impersonations} />,
              tone: "warning",
            },
            {
              icon: <Receipt size={16} />,
              label: "Subscriptions past due",
              href: "/platform/billing/subscriptions",
              count: pastDueSubs,
              value: <Count value={pastDueSubs} />,
              tone: "warning",
            },
            {
              icon: <AlertTriangle size={16} />,
              label: "Suspended tenants",
              href: "/platform/tenants",
              count: suspendedTenants,
              value: <Count value={suspendedTenants} />,
              tone: "danger",
            },
            {
              icon: <AlertTriangle size={16} />,
              label: "Overdue invoices",
              href: "/platform/billing/invoices",
              count: overdueInvoices,
              value: <Count value={overdueInvoices} />,
              tone: "danger",
            },
          ]}
        />
      ) : null}

      <QuickLinks
        items={[
          {
            icon: <Building2 size={18} />,
            label: "Tenants",
            description: "SACCOs & lifecycle",
            href: "/platform/tenants",
          },
          {
            icon: <UserCog size={18} />,
            label: "Users",
            description: "Platform staff & roles",
            href: "/platform/users",
          },
          {
            icon: <Receipt size={18} />,
            label: "Billing",
            description: "Invoices & payments",
            href: "/platform/billing/invoices",
          },
          {
            icon: <FileText size={18} />,
            label: "Approvals",
            description: "Maker-checker queue",
            href: "/platform/approvals",
          },
        ]}
      />
    </div>
  );
}
