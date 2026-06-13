import { notFound, redirect } from "next/navigation";
import { Card } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { SuspendTenantForm } from "./_components/SuspendTenantForm";

export const metadata = { title: "Suspend Tenant" };

export default async function SuspendTenantPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.write");

  const { data } = await (
    resources.tenants.get(id) as Promise<{ data?: TenantOut; error?: unknown }>
  );
  if (!data) notFound();
  // Already-suspended tenants have nothing to suspend — send back to detail.
  if (data.status === "suspended") redirect(`/platform/tenants/${id}`);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Suspend {data.name}</h1>
      <Card className="p-6">
        <p className="mb-4 text-[var(--text-secondary)]">
          Suspending blocks all tenant access (402/403 on tenant requests). This
          creates an approval request — another platform user must approve before
          the tenant is suspended.
        </p>
        <SuspendTenantForm tenant={data} />
      </Card>
    </div>
  );
}
