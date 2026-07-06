import {
  AlertTriangle,
  Banknote,
  CheckCircle2,
  FileText,
  PiggyBank,
  PieChart,
  Users,
} from "lucide-react";
import { Count, FormattedDateTime, Money } from "@sacco/ui";
import type { TenantDashboardStatsOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { DashboardHero } from "@/components/dashboard/DashboardHero";
import { NeedsAttention } from "@/components/dashboard/NeedsAttention";
import { QuickLinks } from "@/components/dashboard/QuickLinks";
import { StatTile, StatTileGrid } from "@/components/dashboard/StatTile";

const DASH = "—";

function activeLoanCount(byStatus: Record<string, number>): number {
  return (
    (byStatus["disbursing"] ?? 0) +
    (byStatus["disbursed"] ?? 0) +
    (byStatus["in_arrears"] ?? 0)
  );
}

export default async function TenantDashboard() {
  const { resources } = await getTenantPageContext();

  const { data } = await (
    resources.dashboard.tenantStats() as Promise<{
      data?: TenantDashboardStatsOut;
      error?: unknown;
    }>
  );

  const loansInArrears = data?.loans_by_status["in_arrears"] ?? 0;

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
          href="/credit/loans"
          hint="Principal balance"
        >
          {data ? <Money amount={data.loans_outstanding_principal} /> : DASH}
        </StatTile>
        <StatTile
          label="Active loans"
          icon={<CheckCircle2 size={18} />}
          href="/credit/loans"
          hint="In repayment"
        >
          {data ? <Count value={activeLoanCount(data.loans_by_status)} /> : DASH}
        </StatTile>
      </StatTileGrid>

      {data ? (
        <NeedsAttention
          items={[
            {
              icon: <CheckCircle2 size={16} />,
              label: "Approvals awaiting your decision",
              href: "/approvals",
              count: data.approvals_pending,
              value: <Count value={data.approvals_pending} />,
              tone: "info",
            },
            {
              icon: <FileText size={16} />,
              label: "Loan applications to review",
              href: "/credit/applications",
              count: data.applications_pending,
              value: <Count value={data.applications_pending} />,
              tone: "info",
            },
            {
              icon: <AlertTriangle size={16} />,
              label: "Loans in arrears",
              href: "/credit/loans",
              count: loansInArrears,
              value: <Count value={loansInArrears} />,
              tone: "danger",
            },
            {
              icon: <AlertTriangle size={16} />,
              label: "Members in arrears",
              href: "/members",
              count: data.members_in_arrears,
              value: <Count value={data.members_in_arrears} />,
              tone: "warning",
            },
          ]}
        />
      ) : null}

      <QuickLinks
        items={[
          {
            icon: <Users size={18} />,
            label: "Members",
            description: "Directory & KYC",
            href: "/members",
          },
          {
            icon: <PiggyBank size={18} />,
            label: "Savings",
            description: "Accounts & transactions",
            href: "/savings/accounts",
          },
          {
            icon: <Banknote size={18} />,
            label: "Loans",
            description: "Portfolio & repayments",
            href: "/credit/loans",
          },
          {
            icon: <PieChart size={18} />,
            label: "Reports",
            description: "Portfolio & statements",
            href: "/reports",
          },
        ]}
      />
    </div>
  );
}
