import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { NewTenantWizard } from "./_components/NewTenantWizard";

export const metadata = { title: "New Tenant" };

export default async function NewTenantPage() {
  const { user } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.create");

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">New tenant</h1>
      <NewTenantWizard />
    </div>
  );
}
