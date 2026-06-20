import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { CreateTenantUserForm } from "./_components/CreateTenantUserForm";

export const metadata = { title: "Add tenant user" };

export default async function NewTenantUserPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.users.write");

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Add user</h1>
      <CreateTenantUserForm tenantId={id} />
    </div>
  );
}
