// admin/apps/portal/app/platform/(authed)/billing/plans/page.tsx
import Link from "next/link";
import { Button, Card } from "@sacco/ui";
import type { SubscriptionPlanOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { BillingTabs } from "../_components/BillingTabs";
import { PlansTable } from "./_components/PlansTable";

export const metadata = { title: "Plans" };

export default async function BillingPlansPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.read");

  // resources.billing.listPlans is typed Promise<never>; cast to the real shape.
  const { data } = await (
    resources.billing.listPlans() as Promise<{
      data?: SubscriptionPlanOut[];
      error?: unknown;
    }>
  );
  const rows = data ?? [];
  const canWrite = userHasPermission(user, "billing.write");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Billing</h1>
        {canWrite ? (
          <Button asChild>
            <Link href="/platform/billing/plans/new">New plan</Link>
          </Button>
        ) : null}
      </div>
      <BillingTabs />
      <Card className="p-0">
        <PlansTable rows={rows} />
      </Card>
    </div>
  );
}
