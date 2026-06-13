import { notFound } from "next/navigation";
import type { TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import {
  ImpersonateTenantPanel,
  type ActiveImpersonation,
} from "./_components/ImpersonateTenantPanel";

export const metadata = { title: "Impersonate Tenant" };

interface ImpersonationOut {
  id: string;
  tenant_id: string;
  expires_at: string;
  ended_at: string | null;
  revoked_at: string | null;
}

export default async function ImpersonateTenantPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "impersonation.start");

  const { data: tenant } = await (
    resources.tenants.get(id) as Promise<{ data?: TenantOut; error?: unknown }>
  );
  if (!tenant) notFound();

  // The operator's active impersonations, filtered to this tenant and still live.
  const { data: active } = await (
    resources.impersonations.listActive() as Promise<{
      data?: ImpersonationOut[];
      error?: unknown;
    }>
  );
  const activeForTenant: ActiveImpersonation[] = (active ?? [])
    .filter((imp) => imp.tenant_id === id && !imp.ended_at && !imp.revoked_at)
    .map((imp) => ({ id: imp.id, expires_at: imp.expires_at }));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Impersonate {tenant.name}</h1>
      <ImpersonateTenantPanel tenant={tenant} activeForTenant={activeForTenant} />
    </div>
  );
}
