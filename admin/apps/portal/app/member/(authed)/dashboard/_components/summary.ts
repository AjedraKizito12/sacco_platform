// Pure derivation of the member dashboard's headline figures and "needs
// attention" counts from the four /member/* list responses. Kept free of React
// so it can be unit-tested directly.

interface SavingsRow {
  available_balance?: string;
  balance?: string;
}
interface ShareRow {
  shares_held: number;
  total_value: string;
}
interface LoanRow {
  status: string;
}
interface FeeRow {
  status: string;
  amount: string;
}

export interface MemberSummaryInput {
  savings: SavingsRow[];
  shares: ShareRow[];
  loans: LoanRow[];
  fees: FeeRow[];
}

export interface MemberSummary {
  savingsTotal: string;
  sharesHeld: number;
  sharesValue: string;
  activeLoans: number;
  loansInArrears: number;
  feesOutstanding: string;
}

const ACTIVE_LOAN_STATUSES = ["disbursed", "in_arrears"];
const SETTLED_FEE_STATUSES = ["paid", "waived", "cancelled"];

function sum(values: string[]): string {
  return values.reduce((acc, v) => acc + Number(v || "0"), 0).toFixed(2);
}

export function computeMemberSummary(input: MemberSummaryInput): MemberSummary {
  const savingsTotal = sum(
    input.savings.map((a) => a.available_balance ?? a.balance ?? "0"),
  );
  const sharesHeld = input.shares.reduce((acc, s) => acc + (s.shares_held ?? 0), 0);
  const sharesValue = sum(input.shares.map((s) => s.total_value ?? "0"));
  const activeLoans = input.loans.filter((l) =>
    ACTIVE_LOAN_STATUSES.includes(l.status),
  ).length;
  const loansInArrears = input.loans.filter((l) => l.status === "in_arrears").length;
  const feesOutstanding = sum(
    input.fees
      .filter((f) => !SETTLED_FEE_STATUSES.includes(f.status))
      .map((f) => f.amount),
  );

  return {
    savingsTotal,
    sharesHeld,
    sharesValue,
    activeLoans,
    loansInArrears,
    feesOutstanding,
  };
}
