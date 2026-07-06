import {
  AlertTriangle,
  Banknote,
  CheckCircle2,
  FileText,
  PiggyBank,
  PieChart,
  Users,
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
  LoanApplicationOut,
  MemberOut,
  TenantDashboardStatsOut,
} from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { NeedsAttention } from "@/components/dashboard/NeedsAttention";
import { QuickLinks } from "@/components/dashboard/QuickLinks";
import { RecentList } from "@/components/dashboard/RecentList";
import { StatTile, StatTileGrid } from "@/components/dashboard/StatTile";
import { deltaPct, toChartData } from "@/components/dashboard/trend";

const DASH = "—";

function activeLoanCount(byStatus: Record<string, number>): number {
  return (
    (byStatus["disbursing"] ?? 0) +
    (byStatus["disbursed"] ?? 0) +
    (byStatus["in_arrears"] ?? 0)
  );
}

function statusSegments(byStatus: Record<string, number>) {
  return Object.entries(byStatus).map(([label, value]) => ({ label, value }));
}

export default async function TenantDashboard() {
  const { resources } = await getTenantPageContext();

  const [statsRes, appsRes, membersRes] = await Promise.all([
    resources.dashboard.tenantStats() as Promise<{
      data?: TenantDashboardStatsOut;
      error?: unknown;
    }>,
    resources.credit.listApplications({}) as Promise<{
      data?: LoanApplicationOut[];
      error?: unknown;
    }>,
    resources.members.list({}) as Promise<{ data?: MemberOut[]; error?: unknown }>,
  ]);
  const data = statsRes.data;

  const loansInArrears = data?.loans_by_status["in_arrears"] ?? 0;
  const savingsDelta = data ? deltaPct(data.savings_trend) : null;

  const memberById = new Map((membersRes.data ?? []).map((m) => [m.id, m]));
  const recentApplications = [...(appsRes.data ?? [])]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 5)
    .map((a) => {
      const m = memberById.get(a.member_id);
      return {
        id: a.id,
        primary: m ? m.full_name : a.member_id,
        secondary: <StatusBadge entity="loan_application" status={a.status} />,
        trailing: <Money amount={a.requested_amount} />,
        href: `/credit/applications`,
      };
    });
  const recentMembers = [...(membersRes.data ?? [])]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 5)
    .map((m) => ({
      id: m.id,
      primary: m.full_name,
      secondary: m.member_number,
      trailing: <StatusBadge entity="member" status={m.status} />,
      href: `/members/${m.id}`,
    }));

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

      <StatTileGrid>
        <StatTile
          label="Total savings"
          icon={<PiggyBank size={18} />}
          href="/savings/accounts"
          delta={savingsDelta}
          deltaLabel="vs last month"
        >
          {data ? <Money amount={data.total_savings} /> : DASH}
        </StatTile>
        <StatTile
          label="Total members"
          icon={<Users size={18} />}
          href="/members"
          hint={data ? `+${data.members_new_this_month} this month` : undefined}
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

      <div className="grid gap-4 md:grid-cols-2">
        <ChartCard title="Savings growth" subtitle="Last 6 months" seeAllHref="/savings/accounts">
          <TrendAreaChart
            data={toChartData(data?.savings_trend ?? [])}
            ariaLabel="Savings growth over the last six months"
            valueFormat={{ kind: "money", currency: "UGX" }}
          />
        </ChartCard>
        <ChartCard title="Loan disbursements" subtitle="Last 6 months" seeAllHref="/credit/loans">
          <TrendAreaChart
            data={toChartData(data?.disbursement_trend ?? [])}
            ariaLabel="Loan disbursements over the last six months"
            valueFormat={{ kind: "money", currency: "UGX" }}
          />
        </ChartCard>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <ChartCard title="Loans by status" seeAllHref="/credit/loans">
          <CompositionDonut
            data={statusSegments(data?.loans_by_status ?? {})}
            emptyLabel="No loans yet"
          />
        </ChartCard>
        <ChartCard title="Members by status" seeAllHref="/members">
          <CompositionBar
            data={statusSegments(data?.members ?? {})}
            emptyLabel="No members yet"
          />
        </ChartCard>
      </div>

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

      <div className="grid gap-4 md:grid-cols-2">
        <ChartCard title="Recent applications" seeAllHref="/credit/applications">
          <RecentList items={recentApplications} emptyLabel="No applications yet" />
        </ChartCard>
        <ChartCard title="Recent members" seeAllHref="/members">
          <RecentList items={recentMembers} emptyLabel="No members yet" />
        </ChartCard>
      </div>

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
