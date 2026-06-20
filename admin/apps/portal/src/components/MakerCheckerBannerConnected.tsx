import { FormattedDateTime, MakerCheckerBanner } from "@sacco/ui";
import type { ApprovalRequestOut, PlatformUserOut } from "@sacco/schemas";
import { operationLabel } from "@sacco/schemas";
import { getPlatformPageContext } from "@/auth/server-page-context";
import { APPROVAL_SUBJECTS, findOpenApproval } from "@/lib/approval-subjects";

/**
 * Server component that renders the maker-checker banner when this record has
 * an open pending approval, else nothing. Sibling to AuditBarConnected; uses
 * the existing /platform/approvals list (no new endpoint).
 */
export async function MakerCheckerBannerConnected({
  entityType,
  entityId,
}: {
  entityType: string;
  entityId: string;
}) {
  if (!APPROVAL_SUBJECTS[entityType]) return null;

  const { resources } = await getPlatformPageContext();
  const { data } = await (
    resources.makerChecker.listPlatform({ status: "pending" }) as Promise<{
      data?: ApprovalRequestOut[];
      error?: unknown;
    }>
  );
  const open = findOpenApproval(entityType, entityId, data ?? []);
  if (!open) return null;

  const { data: users } = await (
    resources.admin.listUsers() as Promise<{ data?: PlatformUserOut[]; error?: unknown }>
  );
  const requester = (users ?? []).find((u) => u.id === open.requested_by);
  const requesterName = requester ? requester.full_name || requester.email : open.requested_by;

  return (
    <MakerCheckerBanner
      approvalRequestId={open.id}
      operationLabel={operationLabel(open.operation_type)}
      requesterName={requesterName}
      requestedAt={<FormattedDateTime value={open.requested_at} />}
      quorumRequired={open.required_approvals}
      quorumCurrent={open.current_approvals}
      action={
        <a
          href={`/platform/approvals/${open.id}`}
          className="text-[13px] underline underline-offset-2"
        >
          Review
        </a>
      }
    />
  );
}
