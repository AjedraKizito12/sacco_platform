// admin/apps/portal/app/(tenant-authed)/credit/payroll/[id]/page.tsx
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { Card, Count, Money, StatusBadge } from "@sacco/ui";
import type { PayrollBatchOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { RejectPayrollBatchButton } from "./_components/RejectPayrollBatchButton";

export const metadata = { title: "Payroll batch" };

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  );
}

export default async function PayrollBatchDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getTenantPageContext();
  const { data: batch } = await (resources.credit.getPayrollBatch(id) as Promise<{
    data?: PayrollBatchOut;
    error?: unknown;
  }>);
  if (!batch) notFound();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-[var(--text-h3)] font-semibold">{batch.reference}</h1>
          <StatusBadge entity="payroll_batch" status={batch.status} />
        </div>
        <RejectPayrollBatchButton batchId={id} status={batch.status} />
      </div>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Summary</h2>
        <Row label="Total rows"><Count value={batch.total_rows} /></Row>
        <Row label="Matched"><Count value={batch.matched_rows} /></Row>
        <Row label="Unmatched"><Count value={batch.unmatched_rows} /></Row>
        <Row label="Total amount"><Money amount={batch.total_amount} /></Row>
        <Row label="Source format">{batch.source_format}</Row>
      </Card>
    </div>
  );
}
