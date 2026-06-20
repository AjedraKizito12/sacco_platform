import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { Card, FormattedDateTime, StatusBadge } from "@sacco/ui";
import { AuditBarConnected } from "@/components/AuditBarConnected";
import type { ApprovalRequestDetailOut, PlatformUserOut } from "@sacco/schemas";
import { operationLabel } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { PayloadView } from "./_components/PayloadView";
import { ApprovalActions } from "./_components/ApprovalActions";

export const metadata = { title: "Approval request" };

function label(u: PlatformUserOut | undefined, id: string): string {
  if (!u) return id;
  return u.full_name.length > 0 ? u.full_name : u.email;
}

export default async function ApprovalDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "approvals.read");

  const { data } = await (
    resources.makerChecker.getPlatform(id) as Promise<{
      data?: ApprovalRequestDetailOut;
      error?: unknown;
    }>
  );
  if (!data) notFound();

  const { data: users } = await (
    resources.admin.listUsers() as Promise<{ data?: PlatformUserOut[]; error?: unknown }>
  );
  const usersById = new Map((users ?? []).map((u) => [u.id, u]));

  // "Before" state for the update_sensitive diff only.
  let before: Record<string, unknown> | undefined;
  if (data.operation_type === "platform_user.update_sensitive") {
    const targetId = data.payload["user_id"];
    if (typeof targetId === "string") {
      const { data: target } = await (
        resources.admin.getUser(targetId) as Promise<{
          data?: PlatformUserOut;
          error?: unknown;
        }>
      );
      if (target) {
        before = { is_active: target.is_active, is_superuser: target.is_superuser };
      }
    }
  }

  const subjectLabel = operationLabel(data.operation_type);
  const canApprove = userHasPermission(user, "approvals.approve");

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
          canApprove={canApprove}
          subjectLabel={subjectLabel}
        />
      </div>

      <Card className="flex flex-col gap-3 p-6">
        <Row
          label="Requested by"
          value={label(usersById.get(data.requested_by), data.requested_by)}
        />
        <Row label="Requested" value={<FormattedDateTime value={data.requested_at} />} />
        {data.rejection_reason ? (
          <Row label="Rejection reason" value={data.rejection_reason} />
        ) : null}
      </Card>

      <Card className="flex flex-col gap-2 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Details</h2>
        <PayloadView
          operationType={data.operation_type}
          payload={data.payload}
          {...(before !== undefined ? { before } : {})}
        />
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
                    {label(usersById.get(a.actor_user_id), a.actor_user_id)}{" "}
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

      <AuditBarConnected entityType="approval_request" entityId={data.id} />
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
