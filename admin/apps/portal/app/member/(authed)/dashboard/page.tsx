import { getMemberPageContext } from "@/auth/server-page-context";
import { SummaryTiles } from "./_components/SummaryTiles";

export default async function MemberDashboard() {
  const { member, resources } = await getMemberPageContext();
  const [savings, shares, loans, fees] = await Promise.all([
    resources.member.listSavings(),
    resources.member.listShares(),
    resources.member.listLoans(),
    resources.member.listFees(),
  ]);

  const savingsRows = (savings.data ?? []) as Array<{
    available_balance?: string;
    balance?: string;
  }>;
  const shareRows = (shares.data ?? []) as Array<{
    shares_held: number;
    total_value: string;
  }>;
  const loanRows = (loans.data ?? []) as Array<{ status: string }>;
  const feeRows = (fees.data ?? []) as Array<{ status: string; amount: string }>;

  const sum = (xs: string[]) =>
    xs.reduce((acc, v) => acc + Number(v || "0"), 0).toFixed(2);

  const savingsTotal = sum(
    savingsRows.map((a) => a.available_balance ?? a.balance ?? "0"),
  );
  const sharesHeld = shareRows.reduce((acc, s) => acc + (s.shares_held ?? 0), 0);
  const sharesValue = sum(shareRows.map((s) => s.total_value ?? "0"));
  const activeLoans = loanRows.filter((l) =>
    ["disbursed", "in_arrears"].includes(l.status),
  ).length;
  const feesOutstanding = sum(
    feeRows
      .filter(
        (f) =>
          f.status !== "paid" &&
          f.status !== "waived" &&
          f.status !== "cancelled",
      )
      .map((f) => f.amount),
  );

  return (
    <div className="space-y-6">
      <h1 className="text-[length:var(--text-h4)] font-semibold">
        Welcome, {member.full_name}
      </h1>
      <SummaryTiles
        savingsTotal={savingsTotal}
        sharesHeld={sharesHeld}
        sharesValue={sharesValue}
        activeLoans={activeLoans}
        feesOutstanding={feesOutstanding}
      />
    </div>
  );
}
