// admin/apps/portal/app/platform/(authed)/billing/subscriptions/page.tsx
import { Card } from "@sacco/ui";
import type { SubscriptionOut, SubscriptionPlanOut, TenantOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { BillingTabs } from "../_components/BillingTabs";
import {
  SubscriptionsTable,
  type SubscriptionRow,
} from "./_components/SubscriptionsTable";

export const metadata = { title: "Subscriptions" };

export default async function BillingSubscriptionsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.read");

  const [{ data: subs }, { data: plans }, { data: tenants }] = await Promise.all([
    resources.billing.listSubscriptions() as Promise<{ data?: SubscriptionOut[]; error?: unknown }>,
    resources.billing.listPlans() as Promise<{ data?: SubscriptionPlanOut[]; error?: unknown }>,
    resources.tenants.list() as Promise<{ data?: TenantOut[]; error?: unknown }>,
  ]);

  const planName = new Map((plans ?? []).map((p) => [p.id, p.name]));
  const tenantName = new Map((tenants ?? []).map((t) => [t.id, t.name]));

  const rows: SubscriptionRow[] = (subs ?? []).map((s) => ({
    id: s.id,
    tenant_id: s.tenant_id,
    tenant_name: tenantName.get(s.tenant_id) ?? s.tenant_id,
    plan_id: s.plan_id,
    plan_name: planName.get(s.plan_id) ?? s.plan_id,
    status: s.status,
    current_period_start: s.current_period_start,
    current_period_end: s.current_period_end,
    next_billing_date: s.next_billing_date,
  }));

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Billing</h1>
      <BillingTabs />
      <Card className="p-0">
        <SubscriptionsTable rows={rows} />
      </Card>
    </div>
  );
}
