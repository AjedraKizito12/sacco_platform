import { notFound } from "next/navigation";
import type {
  OrganizationKycOut,
  TenantLifecycleEventOut,
  TenantOut,
} from "@sacco/schemas";
import { TenantKycSection } from "./_components/TenantKycSection";
import { OffboardingSection } from "./_components/OffboardingSection";
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

  // Offboarding lifecycle timeline (platform schema, always available).
  const lifecycleRes = await (resources.tenants.lifecycle(id) as Promise<{
    data?: TenantLifecycleEventOut[];
    error?: unknown;
  }>);
  const lifecycleEvents = lifecycleRes.data ?? [];

  // Org KYC lives in the tenant schema; the read fails while a tenant is
  // still provisioning (schema/table absent) or failed. KYC is informational
  // (spec: no gating), so a failed read hides the section rather than
  // breaking the whole detail page.
  let kyc: OrganizationKycOut | null = null;
  if (data.status === "active") {
    try {
      const res = await (resources.kyc.getTenantKyc(id) as Promise<{
        data?: OrganizationKycOut;
        error?: unknown;
      }>);
      kyc = res.data ?? null;
    } catch {
      kyc = null;
    }
  }

  return (
    <TenantDetail
      tenant={data}
      canRetry={userHasPermission(user, "platform.tenants.write")}
      canImpersonate={userHasPermission(user, "impersonation.start")}
      canAssignPlan={userHasPermission(user, "billing.write")}
      canViewAudit={userHasPermission(user, "audit.read")}
      canManageUsers={userHasPermission(user, "platform.tenants.users.read")}
      auditBar={<AuditBarConnected entityType="tenant" entityId={data.id} />}
      makerCheckerBanner={<MakerCheckerBannerConnected entityType="tenant" entityId={data.id} />}
      offboardingSection={
        <OffboardingSection
          tenant={data}
          events={lifecycleEvents}
          canOffboard={userHasPermission(user, "platform.tenants.offboard")}
        />
      }
      kycSection={
        kyc ? (
          <TenantKycSection
            tenantId={data.id}
            initial={kyc}
            canVerify={userHasPermission(user, "platform.tenants.write")}
          />
        ) : null
      }
    />
  );
}
