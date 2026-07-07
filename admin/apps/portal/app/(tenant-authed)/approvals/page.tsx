import type { ApprovalRequestOut } from "@sacco/schemas";
import { operationLabel } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { ApprovalsTable, type ApprovalRow } from "./_components/ApprovalsTable";

export const metadata = { title: "Approvals" };

function toRows(requests: ApprovalRequestOut[], currentUserId: string): ApprovalRow[] {
  return requests.map((r) => ({
    id: r.id,
    operation_type: r.operation_type,
    operation_label: operationLabel(r.operation_type),
    status: r.status,
    current_approvals: r.current_approvals,
    required_approvals: r.required_approvals,
    requested_by_label: r.requested_by === currentUserId ? "you" : r.requested_by,
    requested_at: r.requested_at,
  }));
}

export default async function ApprovalsInboxPage() {
  const { user, resources } = await getTenantPageContext();
  const { data: requests } = await (resources.makerChecker.listTenant({}) as Promise<{
    data?: ApprovalRequestOut[];
    error?: unknown;
  }>);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Approvals</h1>
        <a href="/approvals/my-submissions" className="text-[var(--text-link)]">
          My submissions
        </a>
      </div>
      <ApprovalsTable rows={toRows(requests ?? [], user.id)} />
    </div>
  );
}
