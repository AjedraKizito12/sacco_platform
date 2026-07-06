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

  return <CreateTenantUserForm tenantId={id} />;
}
