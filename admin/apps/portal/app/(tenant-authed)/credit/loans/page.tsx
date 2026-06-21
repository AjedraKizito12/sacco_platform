// admin/apps/portal/app/(tenant-authed)/credit/loans/page.tsx
import Link from "next/link";
import { Button } from "@sacco/ui";
import type { LoanOut, MemberOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { LoansTable, type LoanRow } from "./_components/LoansTable";

export const metadata = { title: "Loans" };

export default async function LoansPage() {
  const { resources } = await getTenantPageContext();
  const [{ data: loans }, { data: members }] = await Promise.all([
    resources.credit.listLoans({}) as Promise<{ data?: LoanOut[]; error?: unknown }>,
    resources.members.list({}) as Promise<{ data?: MemberOut[]; error?: unknown }>,
  ]);

  const memberById = new Map((members ?? []).map((m) => [m.id, m]));
  const rows: LoanRow[] = (loans ?? []).map((l) => {
    const m = memberById.get(l.member_id);
    return {
      id: l.id,
      loan_reference: l.loan_reference,
      member_label: m ? `${m.full_name} (${m.member_number})` : l.member_id,
      principal_amount: l.principal_amount,
      outstanding_principal: l.outstanding_principal,
      status: l.status,
    };
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Loans</h1>
        <Button asChild variant="secondary">
          <Link href="/credit">Products</Link>
        </Button>
      </div>
      <LoansTable rows={rows} />
    </div>
  );
}
