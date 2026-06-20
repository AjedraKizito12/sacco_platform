import Link from "next/link";
import { Button } from "@sacco/ui";
import type { TenantUserOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { TenantUsersTable } from "./_components/TenantUsersTable";

export const metadata = { title: "Tenant users" };

export default async function TenantUsersPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.users.read");

  const { data } = await (
    resources.tenants.listUsers(id) as Promise<{ data?: TenantUserOut[]; error?: unknown }>
  );
  const canWrite = userHasPermission(user, "platform.tenants.users.write");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Tenant users</h1>
        {canWrite ? (
          <Button asChild>
            <Link href={`/platform/tenants/${id}/users/new`}>Add user</Link>
          </Button>
        ) : null}
      </div>
      <TenantUsersTable rows={data ?? []} tenantId={id} />
    </div>
  );
}
