import { AlertTriangle, Banknote, Receipt, PiggyBank, User } from "lucide-react";
import { Count, Money } from "@sacco/ui";
import { getMemberPageContext } from "@/auth/server-page-context";
import { NeedsAttention } from "@/components/dashboard/NeedsAttention";
import { QuickLinks } from "@/components/dashboard/QuickLinks";
import { SummaryTiles } from "./_components/SummaryTiles";
import { computeMemberSummary } from "./_components/summary";

export default async function MemberDashboard() {
  const { member, resources } = await getMemberPageContext();
  const [savings, shares, loans, fees] = await Promise.all([
    resources.member.listSavings(),
    resources.member.listShares(),
    resources.member.listLoans(),
    resources.member.listFees(),
  ]);

  const summary = computeMemberSummary({
    savings: (savings.data ?? []) as never[],
    shares: (shares.data ?? []) as never[],
    loans: (loans.data ?? []) as never[],
    fees: (fees.data ?? []) as never[],
  });

  return (
    <div className="space-y-6">
      <h1 className="text-[length:var(--text-h4)] font-semibold">
        Welcome, {member.full_name}
      </h1>

      <SummaryTiles
        savingsTotal={summary.savingsTotal}
        sharesHeld={summary.sharesHeld}
        sharesValue={summary.sharesValue}
        activeLoans={summary.activeLoans}
        feesOutstanding={summary.feesOutstanding}
      />

      {/* Read-only portal: nudges are informational, never transactional. */}
      <NeedsAttention
        allClearLabel="You're all caught up — nothing needs your attention."
        items={[
          {
            icon: <Receipt size={16} />,
            label: "Fees outstanding",
            href: "/member/fees",
            count: Number(summary.feesOutstanding),
            value: <Money amount={summary.feesOutstanding} />,
            tone: "warning",
          },
          {
            icon: <AlertTriangle size={16} />,
            label: "Loans in arrears — contact your SACCO",
            href: "/member/loans",
            count: summary.loansInArrears,
            value: <Count value={summary.loansInArrears} />,
            tone: "danger",
          },
        ]}
      />

      <QuickLinks
        items={[
          {
            icon: <PiggyBank size={18} />,
            label: "Savings",
            description: "Balances & history",
            href: "/member/savings",
          },
          {
            icon: <PiggyBank size={18} />,
            label: "Shares",
            description: "Holdings & value",
            href: "/member/shares",
          },
          {
            icon: <Banknote size={18} />,
            label: "Loans",
            description: "Repayments & schedule",
            href: "/member/loans",
          },
          {
            icon: <Receipt size={18} />,
            label: "Fees",
            description: "Assessments & dues",
            href: "/member/fees",
          },
          {
            icon: <User size={18} />,
            label: "Profile",
            description: "Your details",
            href: "/member/profile",
          },
        ]}
      />
    </div>
  );
}
