import { notFound } from "next/navigation";
import type { TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { AuditBarConnected } from "@/components/AuditBarConnected";
import { MakerCheckerBannerConnected } from "@/components/MakerCheckerBannerConnected";
import { TenantDetail } from "./_components/TenantDetail";

export const metadata = { title: "Tenant" };

export default async function TenantDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "platform.tenants.read");

  // resources.tenants.get is typed Promise<never> (as-never paths in
  // tenants.ts); cast to the real { data, error } shape.
  const { data } = await (
    resources.tenants.get(id) as Promise<{ data?: TenantOut; error?: unknown }>
  );
  if (!data) notFound();

  return (
    <TenantDetail
      tenant={data}
      canRetry={userHasPermission(user, "platform.tenants.write")}
      canImpersonate={userHasPermission(user, "impersonation.start")}
      canAssignPlan={userHasPermission(user, "billing.write")}
      canViewAudit={userHasPermission(user, "audit.read")}
      auditBar={<AuditBarConnected entityType="tenant" entityId={data.id} />}
      makerCheckerBanner={<MakerCheckerBannerConnected entityType="tenant" entityId={data.id} />}
    />
  );
}
