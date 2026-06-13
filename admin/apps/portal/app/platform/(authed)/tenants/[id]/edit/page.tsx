import { notFound } from "next/navigation";
import type { TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { EditTenantForm } from "./_components/EditTenantForm";

export const metadata = { title: "Edit Tenant" };

export default async function EditTenantPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.write");

  // resources.tenants.get is typed Promise<never>; cast to { data, error }.
  const { data } = await (
    resources.tenants.get(id) as Promise<{ data?: TenantOut; error?: unknown }>
  );
  if (!data) notFound();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Edit tenant</h1>
      <EditTenantForm tenant={data} />
    </div>
  );
}
