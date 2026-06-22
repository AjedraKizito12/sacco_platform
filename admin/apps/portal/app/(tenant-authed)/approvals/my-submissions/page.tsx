import type { ApprovalRequestOut } from "@sacco/schemas";
import { operationLabel } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { ApprovalsTable, type ApprovalRow } from "../_components/ApprovalsTable";

export const metadata = { title: "My submissions" };

export default async function MySubmissionsPage() {
  const { user, resources } = await getTenantPageContext();
  const { data: requests } = await (
    resources.makerChecker.listTenant({ requested_by: user.id }) as Promise<{
      data?: ApprovalRequestOut[];
      error?: unknown;
    }>
  );

  const rows: ApprovalRow[] = (requests ?? []).map((r) => ({
    id: r.id,
    operation_type: r.operation_type,
    operation_label: operationLabel(r.operation_type),
    status: r.status,
    current_approvals: r.current_approvals,
    required_approvals: r.required_approvals,
    requested_by_label: "you",
    requested_at: r.requested_at,
  }));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">My submissions</h1>
      <ApprovalsTable rows={rows} />
    </div>
  );
}
