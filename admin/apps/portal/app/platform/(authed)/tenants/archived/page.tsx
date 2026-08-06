import { Card } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { ArchivedTenantsTable } from "./_components/ArchivedTenantsTable";

export const metadata = { title: "Archived tenants" };

export default async function ArchivedTenantsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.read");

  // resources.tenants.listArchived is typed Promise<never>; cast to the real shape.
  const { data } = await (
    resources.tenants.listArchived() as Promise<{
      data?: TenantOut[];
      error?: unknown;
    }>
  );
  const rows = data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Archived tenants</h1>
      </div>
      <Card className="p-0">
        <ArchivedTenantsTable rows={rows} />
      </Card>
    </div>
  );
}
