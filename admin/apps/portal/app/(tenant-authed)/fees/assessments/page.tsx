// admin/apps/portal/app/(tenant-authed)/fees/assessments/page.tsx
import Link from "next/link";
import { Button } from "@sacco/ui";
import type { FeeAssessmentOut, FeeTypeOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { AssessmentsTable, type AssessmentRow } from "./_components/AssessmentsTable";

export const metadata = { title: "Fee assessments" };

export default async function FeeAssessmentsPage() {
  const { resources } = await getTenantPageContext();
  const [{ data: assessments }, { data: feeTypes }] = await Promise.all([
    resources.fees.listAssessments({}) as Promise<{
      data?: FeeAssessmentOut[];
      error?: unknown;
    }>,
    resources.fees.listTypes({}) as Promise<{ data?: FeeTypeOut[]; error?: unknown }>,
  ]);

  const feeTypeById = new Map((feeTypes ?? []).map((t) => [t.id, t]));
  const rows: AssessmentRow[] = (assessments ?? []).map((a) => ({
    id: a.id,
    fee_type_name: feeTypeById.get(a.fee_type_id)?.name ?? a.fee_type_id,
    target_type: a.target_type,
    amount: a.amount,
    period_start: a.period_start,
    status: a.status,
  }));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Fee assessments</h1>
        <div className="flex gap-2">
          <Button asChild variant="secondary">
            <Link href="/fees/types">Fee types</Link>
          </Button>
          <Button asChild>
            <Link href="/fees/assessments/new">New assessment</Link>
          </Button>
        </div>
      </div>
      <AssessmentsTable rows={rows} />
    </div>
  );
}
