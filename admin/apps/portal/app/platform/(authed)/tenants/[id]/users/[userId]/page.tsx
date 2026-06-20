import type { ReactNode } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Button, Card, FormattedDate, RelativeTime, StatusBadge } from "@sacco/ui";
import { tenantUserRoleLabel, type TenantUserOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { ResetPasswordButton } from "./_components/ResetPasswordButton";

export const metadata = { title: "Tenant user" };

export default async function TenantUserDetailPage({
  params,
}: {
  params: Promise<{ id: string; userId: string }>;
}) {
  const { id, userId } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.users.read");

  const { data } = await (
    resources.tenants.getUser(id, userId) as Promise<{ data?: TenantUserOut; error?: unknown }>
  );
  if (!data) notFound();

  const canWrite = userHasPermission(user, "platform.tenants.users.write");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">{data.full_name}</h1>
        {canWrite ? (
          <div className="flex items-center gap-2">
            <Button asChild variant="secondary">
              <Link href={`/platform/tenants/${id}/users/${userId}/edit`}>Edit</Link>
            </Button>
            <ResetPasswordButton tenantId={id} userId={userId} />
          </div>
        ) : null}
      </div>

      <Card className="grid grid-cols-2 gap-5 p-6">
        <Row label="Email" value={data.email} />
        <Row label="Role" value={tenantUserRoleLabel(data.is_admin)} />
        <Row
          label="Status"
          value={
            <StatusBadge entity="tenant_user" status={data.is_active ? "active" : "inactive"} />
          }
        />
        <Row
          label="Last login"
          value={data.last_login_at ? <RelativeTime value={data.last_login_at} /> : "Never"}
        />
        <Row label="Created" value={<FormattedDate value={data.created_at} />} />
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[13px] text-[var(--text-tertiary)]">{label}</span>
      <span className="text-[var(--text-primary)]">{value}</span>
    </div>
  );
}
