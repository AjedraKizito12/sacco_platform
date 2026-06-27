import { Card, Money, Percentage, StatusBadge } from "@sacco/ui";
import { getMemberPageContext } from "@/auth/server-page-context";
import {
  MemberScheduleTable,
  type MemberInstallmentRow,
} from "./_components/MemberScheduleTable";
import {
  MemberStatementTable,
  type MemberStatementLine,
} from "./_components/MemberStatementTable";

export const metadata = { title: "Loan" };

interface MemberLoan {
  id: string;
  loan_reference: string;
  status: string;
  principal_amount: string;
  outstanding_principal: string;
  accrued_interest: string;
  annual_interest_rate: string;
}

export default async function MemberLoanDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getMemberPageContext();

  const [loanRes, scheduleRes, statementRes] = await Promise.all([
    resources.member.getLoan(id),
    resources.member.getLoanSchedule(id),
    resources.member.getLoanStatement(id),
  ]);

  const loan = loanRes.data as MemberLoan | undefined;
  if (!loan) {
    return (
      <Card className="p-6">
        <h1 className="text-[var(--text-h4)] font-semibold">Loan not found</h1>
        <p className="mt-2 text-[var(--text-secondary)]">
          This loan does not exist or is not one of yours.
        </p>
      </Card>
    );
  }

  const schedule = (scheduleRes.data ?? []) as MemberInstallmentRow[];
  const statementData = statementRes.data as
    | { lines?: MemberStatementLine[] }
    | undefined;
  const statement = statementData?.lines ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-[var(--text-h3)] font-semibold">
          {loan.loan_reference}
        </h1>
        <StatusBadge entity="loan" status={loan.status} />
      </div>

      <Card className="flex flex-col gap-3 p-6">
        <div className="flex items-baseline justify-between gap-4">
          <span className="text-[var(--text-secondary)]">
            Outstanding principal
          </span>
          <span className="text-[var(--text-h4)] font-semibold">
            <Money amount={loan.outstanding_principal} />
          </span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Principal amount</span>
          <Money amount={loan.principal_amount} />
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Accrued interest</span>
          <Money amount={loan.accrued_interest} />
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Interest rate</span>
          <Percentage value={loan.annual_interest_rate} />
        </div>
      </Card>

      <div className="flex flex-col gap-3">
        <h2 className="text-[var(--text-h5)] font-semibold">
          Repayment schedule
        </h2>
        <MemberScheduleTable rows={schedule} />
      </div>

      <div className="flex flex-col gap-3">
        <h2 className="text-[var(--text-h5)] font-semibold">Statement</h2>
        <MemberStatementTable rows={statement} />
      </div>
    </div>
  );
}
