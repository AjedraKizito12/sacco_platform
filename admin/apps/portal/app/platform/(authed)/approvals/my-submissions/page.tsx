import type { ApprovalRequestOut, PlatformUserOut } from "@sacco/schemas";
import { operationLabel } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { ApprovalsTable, type ApprovalRow } from "../_components/ApprovalsTable";

export const metadata = { title: "My submissions" };

function userLabel(u: PlatformUserOut | undefined, id: string): string {
  if (!u) return id;
  return u.full_name.length > 0 ? u.full_name : u.email;
}

export default async function MySubmissionsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "approvals.read");

  const { data: requests } = await (
    resources.makerChecker.listPlatform({ requested_by: user.id }) as Promise<{
      data?: ApprovalRequestOut[];
      error?: unknown;
    }>
  );
  const { data: users } = await (
    resources.admin.listUsers() as Promise<{ data?: PlatformUserOut[]; error?: unknown }>
  );
  const usersById = new Map((users ?? []).map((u) => [u.id, u]));

  const rows: ApprovalRow[] = (requests ?? []).map((r) => ({
    id: r.id,
    operation_type: r.operation_type,
    operation_label: operationLabel(r.operation_type),
    status: r.status,
    current_approvals: r.current_approvals,
    required_approvals: r.required_approvals,
    requested_by_label: userLabel(usersById.get(r.requested_by), r.requested_by),
    requested_at: r.requested_at,
  }));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">My submissions</h1>
      <ApprovalsTable rows={rows} />
    </div>
  );
}
