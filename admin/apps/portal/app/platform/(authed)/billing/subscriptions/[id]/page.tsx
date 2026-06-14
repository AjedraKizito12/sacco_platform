import { notFound } from "next/navigation";
import { Card, FormattedDate, StatusBadge } from "@sacco/ui";
import type { SubscriptionOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { SubscriptionActions } from "./_components/SubscriptionActions";

export const metadata = { title: "Subscription" };

export default async function SubscriptionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.read");

  const { data } = await (
    resources.billing.getSubscription(id) as Promise<{
      data?: SubscriptionOut;
      error?: unknown;
    }>
  );
  if (!data) notFound();
  const canWrite = userHasPermission(user, "billing.write");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">Subscription</h1>
        <SubscriptionActions subscription={data} canWrite={canWrite} />
      </div>
      <Card className="flex flex-col gap-3 p-6">
        <div className="flex justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Status</span>
          <StatusBadge entity="subscription" status={data.status} />
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Current period</span>
          <span>
            <FormattedDate value={data.current_period_start} /> – <FormattedDate value={data.current_period_end} />
          </span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-[var(--text-secondary)]">Next billing</span>
          <span>
            {data.next_billing_date ? <FormattedDate value={data.next_billing_date} /> : "—"}
          </span>
        </div>
        {data.cancellation_reason ? (
          <div className="flex justify-between gap-4">
            <span className="text-[var(--text-secondary)]">Cancellation reason</span>
            <span>{data.cancellation_reason}</span>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
