// admin/apps/portal/app/platform/(authed)/tenants/[id]/assign-plan/page.tsx
import { notFound } from "next/navigation";
import type { SubscriptionPlanOut, TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { AssignPlanForm } from "./_components/AssignPlanForm";

export const metadata = { title: "Assign plan" };

export default async function AssignPlanPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.write");

  const [{ data: tenant }, { data: plans }] = await Promise.all([
    resources.tenants.get(id) as Promise<{ data?: TenantOut; error?: unknown }>,
    resources.billing.listPlans({ only_active: true }) as Promise<{
      data?: SubscriptionPlanOut[];
      error?: unknown;
    }>,
  ]);
  if (!tenant) notFound();
  // Surface a plans-fetch failure instead of rendering an empty Select with no
  // recourse — the AppErrorBoundary renders the error state.
  if (!plans) throw new Error("Failed to load subscription plans");

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Assign a plan to {tenant.name}</h1>
      <AssignPlanForm tenantId={id} plans={plans} />
    </div>
  );
}
