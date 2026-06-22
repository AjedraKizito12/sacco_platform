import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { Card, FormattedDateTime, StatusBadge } from "@sacco/ui";
import type { ApprovalRequestDetailOut } from "@sacco/schemas";
import { operationLabel } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { PayloadView } from "./_components/PayloadView";
import { ApprovalActions } from "./_components/ApprovalActions";

export const metadata = { title: "Approval request" };

export default async function ApprovalDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getTenantPageContext();

  const { data } = await (resources.makerChecker.getTenant(id) as Promise<{
    data?: ApprovalRequestDetailOut;
    error?: unknown;
  }>);
  if (!data) notFound();

  const subjectLabel = operationLabel(data.operation_type);
  const requestedByLabel = data.requested_by === user.id ? "you" : data.requested_by;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-[var(--text-h3)] font-semibold">{subjectLabel}</h1>
          <StatusBadge entity="approval_request" status={data.status} />
          <span className="text-[var(--text-tertiary)] tabular-nums">
            {data.current_approvals} of {data.required_approvals}
          </span>
        </div>
        <ApprovalActions
          requestId={data.id}
          status={data.status}
          requestedBy={data.requested_by}
          currentUserId={user.id}
          subjectLabel={subjectLabel}
        />
      </div>

      <Card className="flex flex-col gap-3 p-6">
        <Row label="Requested by" value={requestedByLabel} />
        <Row label="Requested" value={<FormattedDateTime value={data.requested_at} />} />
        {data.rejection_reason ? (
          <Row label="Rejection reason" value={data.rejection_reason} />
        ) : null}
      </Card>

      <Card className="flex flex-col gap-2 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Details</h2>
        <PayloadView payload={data.payload} />
      </Card>

      <Card className="flex flex-col gap-2 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Activity</h2>
        {data.actions.length === 0 ? (
          <p className="text-[var(--text-tertiary)]">No actions yet.</p>
        ) : (
          <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
            {data.actions.map((a) => (
              <div key={a.id} className="flex items-start justify-between gap-4 py-2">
                <div className="flex flex-col">
                  <span className="text-[var(--text-primary)]">
                    {a.actor_user_id === user.id ? "you" : a.actor_user_id}{" "}
                    {a.action === "approve" ? "approved" : "rejected"}
                  </span>
                  {a.comment ? (
                    <span className="text-[13px] text-[var(--text-tertiary)]">{a.comment}</span>
                  ) : null}
                </div>
                <FormattedDateTime value={a.acted_at} />
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-[var(--text-primary)]">{value}</span>
    </div>
  );
}
