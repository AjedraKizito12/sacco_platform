// admin/apps/portal/app/(tenant-authed)/credit/applications/page.tsx
import Link from "next/link";
import { Button } from "@sacco/ui";
import type {
  LoanApplicationOut,
  LoanProductOut,
  MemberOut,
} from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { ApplicationsTable, type ApplicationRow } from "./_components/ApplicationsTable";

export const metadata = { title: "Loan applications" };

export default async function LoanApplicationsPage() {
  const { resources } = await getTenantPageContext();
  const [{ data: applications }, { data: members }, { data: products }] =
    await Promise.all([
      resources.credit.listApplications({}) as Promise<{
        data?: LoanApplicationOut[];
        error?: unknown;
      }>,
      resources.members.list({}) as Promise<{ data?: MemberOut[]; error?: unknown }>,
      resources.credit.listProducts({}) as Promise<{
        data?: LoanProductOut[];
        error?: unknown;
      }>,
    ]);

  const memberById = new Map((members ?? []).map((m) => [m.id, m]));
  const productById = new Map((products ?? []).map((p) => [p.id, p]));
  const rows: ApplicationRow[] = (applications ?? []).map((a) => {
    const m = memberById.get(a.member_id);
    return {
      id: a.id,
      member_label: m ? `${m.full_name} (${m.member_number})` : a.member_id,
      product_name: productById.get(a.loan_product_id)?.name ?? a.loan_product_id,
      requested_amount: a.requested_amount,
      requested_term_periods: a.requested_term_periods,
      status: a.status,
    };
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Loan applications</h1>
        <Button asChild>
          <Link href="/credit/applications/new">New application</Link>
        </Button>
      </div>
      <ApplicationsTable rows={rows} />
    </div>
  );
}
