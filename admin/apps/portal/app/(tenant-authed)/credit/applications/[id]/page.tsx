// admin/apps/portal/app/(tenant-authed)/credit/applications/[id]/page.tsx
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import {
  Card,
  Count,
  FormattedDateTime,
  MakerCheckerBanner,
  Money,
  StatusBadge,
} from "@sacco/ui";
import type {
  ApprovalRequestOut,
  GuarantorOut,
  LoanApplicationOut,
  LoanProductOut,
  MemberOut,
} from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { ApplicationActions } from "./_components/ApplicationActions";
import { GuarantorsSection } from "./_components/GuarantorsSection";

export const metadata = { title: "Loan application" };

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  );
}

export default async function LoanApplicationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getTenantPageContext();

  const { data: application } = await (resources.credit.getApplication(id) as Promise<{
    data?: LoanApplicationOut;
    error?: unknown;
  }>);
  if (!application) notFound();

  const [{ data: guarantors }, { data: members }, { data: product }] =
    await Promise.all([
      resources.credit.listGuarantors(id) as Promise<{
        data?: GuarantorOut[];
        error?: unknown;
      }>,
      resources.members.list({}) as Promise<{ data?: MemberOut[]; error?: unknown }>,
      resources.credit.getProduct(application.loan_product_id) as Promise<{
        data?: LoanProductOut;
        error?: unknown;
      }>,
    ]);

  const isPending = application.status === "pending";
  let approvalRequest: ApprovalRequestOut | undefined;
  if (isPending && application.approval_request_id) {
    const { data } = await (resources.makerChecker.getTenant(
      application.approval_request_id,
    ) as Promise<{ data?: ApprovalRequestOut; error?: unknown }>);
    approvalRequest = data;
  }

  const memberById = new Map((members ?? []).map((m) => [m.id, m]));
  const m = memberById.get(application.member_id);
  const memberLabel = m ? `${m.full_name} (${m.member_number})` : application.member_id;
  const memberOptions = (members ?? []).map((mm) => ({
    id: mm.id,
    full_name: mm.full_name,
    member_number: mm.member_number,
  }));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">
          {product?.name ?? "Loan application"}
        </h1>
        <StatusBadge entity="loan_application" status={application.status} />
      </div>

      {isPending && approvalRequest ? (
        <MakerCheckerBanner
          approvalRequestId={approvalRequest.id}
          operationLabel="Loan approval"
          requesterName={approvalRequest.requested_by}
          requestedAt={<FormattedDateTime value={approvalRequest.requested_at} />}
          quorumRequired={approvalRequest.required_approvals}
          quorumCurrent={approvalRequest.current_approvals}
          action={<ApplicationActions applicationId={id} />}
        />
      ) : isPending ? (
        <ApplicationActions applicationId={id} />
      ) : null}

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Details</h2>
        <Row label="Member">{memberLabel}</Row>
        <Row label="Requested amount">
          <Money amount={application.requested_amount} />
        </Row>
        <Row label="Term (periods)">
          <Count value={application.requested_term_periods} />
        </Row>
        <Row label="Purpose">{application.purpose ?? "—"}</Row>
        <Row label="Disbursement destination">{application.disbursement_destination}</Row>
        {application.approved_amount ? (
          <Row label="Approved amount">
            <Money amount={application.approved_amount} />
          </Row>
        ) : null}
        {application.approved_term_periods != null ? (
          <Row label="Approved term">
            <Count value={application.approved_term_periods} />
          </Row>
        ) : null}
        {application.rejection_reason ? (
          <Row label="Rejection reason">{application.rejection_reason}</Row>
        ) : null}
        {application.decided_at ? (
          <Row label="Decided at">
            <FormattedDateTime value={application.decided_at} />
          </Row>
        ) : null}
      </Card>

      <GuarantorsSection
        applicationId={id}
        guarantors={guarantors ?? []}
        members={memberOptions}
      />
    </div>
  );
}
