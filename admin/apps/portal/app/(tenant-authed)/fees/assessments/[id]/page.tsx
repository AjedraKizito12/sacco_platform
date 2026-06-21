// admin/apps/portal/app/(tenant-authed)/fees/assessments/[id]/page.tsx
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { Card, FormattedDate, FormattedDateTime, Money, StatusBadge } from "@sacco/ui";
import type { FeeAssessmentDetailOut, FeeTypeOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { CollectionsTable } from "./_components/CollectionsTable";
import { RecordCollectionButton, type GlAccountOption } from "./_components/RecordCollectionButton";

export const metadata = { title: "Fee assessment" };

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  );
}

export default async function FeeAssessmentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getTenantPageContext();

  const { data: assessment } = await (resources.fees.getAssessment(id) as Promise<{
    data?: FeeAssessmentDetailOut;
    error?: unknown;
  }>);
  if (!assessment) notFound();

  const [{ data: feeType }, { data: accounts }] = await Promise.all([
    resources.fees.getType(assessment.fee_type_id) as Promise<{
      data?: FeeTypeOut;
      error?: unknown;
    }>,
    resources.ledger.listAccounts({}) as Promise<{
      data?: GlAccountOption[];
      error?: unknown;
    }>,
  ]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-[var(--text-h3)] font-semibold">
            {feeType?.name ?? "Fee assessment"}
          </h1>
          <StatusBadge entity="fee_assessment" status={assessment.status} />
        </div>
        <RecordCollectionButton
          assessmentId={id}
          status={assessment.status}
          glAccounts={accounts ?? []}
        />
      </div>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Details</h2>
        <Row label="Target">{assessment.target_type} · {assessment.target_id}</Row>
        <Row label="Amount"><Money amount={assessment.amount} /></Row>
        <Row label="Period start"><FormattedDate value={assessment.period_start} /></Row>
        <Row label="Period end">
          {assessment.period_end ? <FormattedDate value={assessment.period_end} /> : "—"}
        </Row>
        <Row label="Assessed"><FormattedDateTime value={assessment.assessed_at} /></Row>
        <Row label="Due">
          {assessment.due_at ? <FormattedDate value={assessment.due_at} /> : "—"}
        </Row>
        <Row label="Paid">
          {assessment.paid_at ? <FormattedDate value={assessment.paid_at} /> : "—"}
        </Row>
        {assessment.waiver_reason ? (
          <Row label="Waiver reason">{assessment.waiver_reason}</Row>
        ) : null}
      </Card>

      <div className="flex flex-col gap-3">
        <h2 className="text-[var(--text-h5)] font-semibold">Collections</h2>
        <CollectionsTable rows={assessment.collections} />
      </div>
    </div>
  );
}
