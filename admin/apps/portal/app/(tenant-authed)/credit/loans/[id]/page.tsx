// admin/apps/portal/app/(tenant-authed)/credit/loans/[id]/page.tsx
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import {
  Button,
  Card,
  Count,
  FormattedDate,
  Money,
  Percentage,
  StatusBadge,
} from "@sacco/ui";
import type {
  LoanInstallmentOut,
  LoanOut,
  LoanRepaymentOut,
  LoanStatementOut,
  MemberOut,
} from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { RecordRepaymentButton, type GlAccountOption } from "./_components/RecordRepaymentButton";
import { ScheduleTable } from "./_components/ScheduleTable";
import { RepaymentsTable } from "./_components/RepaymentsTable";
import { StatementTable } from "./_components/StatementTable";

export const metadata = { title: "Loan" };

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  );
}

export default async function LoanDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getTenantPageContext();

  const { data: loan } = await (resources.credit.getLoan(id) as Promise<{
    data?: LoanOut;
    error?: unknown;
  }>);
  if (!loan) notFound();

  const [{ data: schedule }, { data: repayments }, { data: statement }, { data: members }, { data: accounts }] =
    await Promise.all([
      resources.credit.getSchedule(id) as Promise<{ data?: LoanInstallmentOut[]; error?: unknown }>,
      resources.credit.listRepayments(id) as Promise<{ data?: LoanRepaymentOut[]; error?: unknown }>,
      resources.credit.getStatement(id) as Promise<{ data?: LoanStatementOut; error?: unknown }>,
      resources.members.list({}) as Promise<{ data?: MemberOut[]; error?: unknown }>,
      resources.ledger.listAccounts({}) as Promise<{ data?: GlAccountOption[]; error?: unknown }>,
    ]);

  const m = (members ?? []).find((mm) => mm.id === loan.member_id);
  const memberLabel = m ? `${m.full_name} (${m.member_number})` : loan.member_id;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-[var(--text-h3)] font-semibold">{loan.loan_reference}</h1>
          <StatusBadge entity="loan" status={loan.status} />
        </div>
        <RecordRepaymentButton loanId={id} glAccounts={accounts ?? []} />
      </div>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Balances</h2>
        <div className="flex items-baseline justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Outstanding principal</span>
          <span className="text-[var(--text-h4)] font-semibold">
            <Money amount={loan.outstanding_principal} />
          </span>
        </div>
        <Row label="Accrued interest"><Money amount={loan.accrued_interest} /></Row>
        <Row label="Accrued penalties"><Money amount={loan.accrued_penalties} /></Row>
      </Card>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Terms</h2>
        <Row label="Member">{memberLabel}</Row>
        <Row label="Principal"><Money amount={loan.principal_amount} /></Row>
        <Row label="Interest rate"><Percentage value={loan.annual_interest_rate} /></Row>
        <Row label="Interest method">{loan.interest_method}</Row>
        <Row label="Repayment frequency">{loan.repayment_frequency}</Row>
        <Row label="Term (periods)"><Count value={loan.term_periods} /></Row>
        <Row label="Disbursement destination">{loan.disbursement_destination}</Row>
        <Row label="Disbursed at">
          {loan.disbursed_at ? <FormattedDate value={loan.disbursed_at} /> : "—"}
        </Row>
        <Row label="First repayment due">
          {loan.first_repayment_due ? <FormattedDate value={loan.first_repayment_due} /> : "—"}
        </Row>
        <Row label="Maturity">
          {loan.maturity_date ? <FormattedDate value={loan.maturity_date} /> : "—"}
        </Row>
      </Card>

      <div className="flex flex-col gap-3">
        <h2 className="text-[var(--text-h5)] font-semibold">Schedule</h2>
        <ScheduleTable rows={schedule ?? []} />
      </div>

      <div className="flex flex-col gap-3">
        <h2 className="text-[var(--text-h5)] font-semibold">Repayments</h2>
        <RepaymentsTable rows={repayments ?? []} />
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 className="text-[var(--text-h5)] font-semibold">Statement</h2>
          <Button asChild variant="secondary">
            <a href={`/api/credit/loans/${id}/statement-pdf`} target="_blank" rel="noopener noreferrer">
              Download PDF
            </a>
          </Button>
        </div>
        <StatementTable rows={statement?.lines ?? []} />
      </div>
    </div>
  );
}
