import { notFound } from "next/navigation";
import type { TenantUserOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { EditTenantUserForm } from "./_components/EditTenantUserForm";

export const metadata = { title: "Edit tenant user" };

export default async function EditTenantUserPage({
  params,
}: {
  params: Promise<{ id: string; userId: string }>;
}) {
  const { id, userId } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.users.write");

  const { data } = await (
    resources.tenants.getUser(id, userId) as Promise<{ data?: TenantUserOut; error?: unknown }>
  );
  if (!data) notFound();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Edit user</h1>
      <EditTenantUserForm tenantId={id} user={data} />
    </div>
  );
}
