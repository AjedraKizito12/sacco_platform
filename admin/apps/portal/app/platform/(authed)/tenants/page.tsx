import Link from "next/link";
import { Button, Card } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { TenantsTable } from "./_components/TenantsTable";

export const metadata = { title: "Tenants" };

export default async function PlatformTenantsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.read");

  // resources.tenants.list is typed Promise<never> because tenants.ts uses
  // `as never` on its openapi-fetch paths; cast to the real openapi-fetch
  // { data, error } shape until those resource types tighten.
  const { data } = await (
    resources.tenants.list() as Promise<{ data?: TenantOut[]; error?: unknown }>
  );
  const rows = data ?? [];
  const canCreate = userHasPermission(user, "platform.tenants.create");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Tenants</h1>
        <div className="flex items-center gap-2">
          <Button asChild variant="secondary">
            <Link href="/platform/tenants/archived">Archived</Link>
          </Button>
          {canCreate ? (
            <Button asChild>
              <Link href="/platform/tenants/new">New tenant</Link>
            </Button>
          ) : null}
        </div>
      </div>
      <Card className="p-0">
        <TenantsTable rows={rows} />
      </Card>
    </div>
  );
}
