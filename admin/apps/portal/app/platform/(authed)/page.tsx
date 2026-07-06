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
import {
  ChartCard,
  CompositionBar,
  CompositionDonut,
  Count,
  FormattedDateTime,
  Money,
  StatusBadge,
  TrendAreaChart,
} from "@sacco/ui";
import type {
  DashboardStatsOut,
  InvoiceOut,
  TenantOut,
} from "@sacco/schemas";
import { getPlatformPageContext } from "@/auth/server-page-context";
import { NeedsAttention } from "@/components/dashboard/NeedsAttention";
import { QuickLinks } from "@/components/dashboard/QuickLinks";
import { RecentList } from "@/components/dashboard/RecentList";
import { StatTile, StatTileGrid } from "@/components/dashboard/StatTile";
import { deltaPct, toChartData } from "@/components/dashboard/trend";

const DASH = "—";

function sumValues(d: Record<string, number>): number {
  return Object.values(d).reduce((a, b) => a + b, 0);
}

function statusSegments(byStatus: Record<string, number>) {
  return Object.entries(byStatus).map(([label, value]) => ({ label, value }));
}

/** MRR can span currencies — the first is the headline, the rest list below. */
function HeroMrr({ mrr }: { mrr: Record<string, string> }): ReactNode {
  const entries = Object.entries(mrr);
  const first = entries[0];
  if (!first) return <Money amount="0" currency="UGX" />;
  return (
    <span className="flex items-baseline gap-2">
      <Money amount={first[1]} currency={first[0]} />
      {entries.slice(1).map(([currency, amount]) => (
        <Money
          key={currency}
          amount={amount}
          currency={currency}
          className="text-[14px] font-normal text-[var(--text-tertiary)]"
        />
      ))}
    </span>
  );
}

export default async function PlatformDashboard() {
  const { resources } = await getPlatformPageContext();

  // dashboard-stats is admin-gated; support/finance users get no data — fall
  // back to placeholders rather than failing. The list calls are best-effort
  // for the same reason.
  const [statsRes, tenantsRes, invoicesRes] = await Promise.all([
    resources.admin.dashboardStats() as Promise<{
      data?: DashboardStatsOut;
      error?: unknown;
    }>,
    resources.tenants.list() as Promise<{ data?: TenantOut[]; error?: unknown }>,
    resources.billing.listInvoices() as Promise<{
      data?: InvoiceOut[];
      error?: unknown;
    }>,
  ]);
  const data = statsRes.data;

  const activeSubs = data
    ? (data.subscriptions["active"] ?? 0) + (data.subscriptions["trialing"] ?? 0)
    : 0;
  const pastDueSubs = data?.subscriptions["past_due"] ?? 0;
  const suspendedTenants = data?.tenants["suspended"] ?? 0;
  const overdueInvoices = data?.invoices_outstanding["overdue"] ?? 0;
  const revenueDelta = data ? deltaPct(data.revenue_trend) : null;

  const recentTenants = [...(tenantsRes.data ?? [])]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 5)
    .map((t) => ({
      id: t.id,
      primary: t.name,
      secondary: t.slug,
      trailing: <StatusBadge entity="tenant" status={t.status} />,
      href: `/platform/tenants/${t.id}`,
    }));
  const recentInvoices = [...(invoicesRes.data ?? [])]
    .slice(0, 5)
    .map((inv) => ({
      id: inv.id,
      primary: inv.invoice_number,
      secondary: <StatusBadge entity="invoice" status={inv.status} />,
      trailing: <Money amount={inv.amount_total} currency={inv.currency} />,
      href: `/platform/billing/invoices/${inv.id}`,
    }));

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

      <StatTileGrid>
        <StatTile
          label="Monthly recurring revenue"
          icon={<Wallet size={18} />}
          href="/platform/billing/subscriptions"
        >
          {data ? <HeroMrr mrr={data.mrr} /> : DASH}
        </StatTile>
        <StatTile
          label="Total tenants"
          icon={<Building2 size={18} />}
          href="/platform/tenants"
          hint={data ? `+${data.tenants_new_this_month} this month` : undefined}
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

      <div className="grid gap-4 md:grid-cols-2">
        <ChartCard
          title="Revenue collected"
          subtitle="Last 6 months"
          seeAllHref="/platform/billing/invoices"
          action={
            revenueDelta !== null ? (
              <span className="text-[13px] font-medium text-[var(--text-tertiary)]">
                {revenueDelta >= 0 ? "+" : ""}
                {revenueDelta.toFixed(1)}% vs last month
              </span>
            ) : undefined
          }
        >
          <TrendAreaChart
            data={toChartData(data?.revenue_trend ?? [])}
            ariaLabel="Revenue collected over the last six months"
            valueFormat={{ kind: "money", currency: "UGX" }}
          />
        </ChartCard>
        <ChartCard title="Tenant growth" subtitle="Last 6 months" seeAllHref="/platform/tenants">
          <TrendAreaChart
            data={toChartData(data?.tenants_trend ?? [])}
            ariaLabel="Cumulative tenant count over the last six months"
            valueFormat={{ kind: "number" }}
          />
        </ChartCard>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <ChartCard title="Subscriptions by status" seeAllHref="/platform/billing/subscriptions">
          <CompositionDonut
            data={statusSegments(data?.subscriptions ?? {})}
            emptyLabel="No subscriptions yet"
          />
        </ChartCard>
        <ChartCard title="Tenants by status" seeAllHref="/platform/tenants">
          <CompositionBar
            data={statusSegments(data?.tenants ?? {})}
            emptyLabel="No tenants yet"
          />
        </ChartCard>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <ChartCard title="Recent tenants" seeAllHref="/platform/tenants">
          <RecentList items={recentTenants} emptyLabel="No tenants yet" />
        </ChartCard>
        <ChartCard title="Recent invoices" seeAllHref="/platform/billing/invoices">
          <RecentList items={recentInvoices} emptyLabel="No invoices yet" />
        </ChartCard>
      </div>

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
