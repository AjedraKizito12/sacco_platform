import type { ReactNode } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AuditBar, Button, Card, Count, Money, StatusBadge } from "@sacco/ui";
import type { SubscriptionPlanOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";

export const metadata = { title: "Plan" };

export default async function PlanDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.read");

  // resources.billing.getPlan is typed Promise<never>; cast to the real shape.
  const { data } = await (
    resources.billing.getPlan(id) as Promise<{
      data?: SubscriptionPlanOut;
      error?: unknown;
    }>
  );
  if (!data) notFound();
  const canWrite = userHasPermission(user, "billing.write");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">{data.name}</h1>
        {canWrite ? (
          <Button asChild variant="secondary">
            <Link href={`/platform/billing/plans/${data.id}/edit`}>Edit</Link>
          </Button>
        ) : null}
      </div>
      <Card className="flex flex-col gap-3 p-6">
        <Row label="Code" value={data.code} />
        <Row
          label="Status"
          value={
            <StatusBadge
              entity="subscription_plan"
              status={data.is_active ? "active" : "inactive"}
            />
          }
        />
        <Row
          label="Base price"
          value={<Money amount={data.base_price} currency={data.currency} />}
        />
        <Row
          label="Per user"
          value={<Money amount={data.per_user_price} currency={data.currency} />}
        />
        <Row
          label="Per member"
          value={
            <Money amount={data.per_member_price} currency={data.currency} />
          }
        />
        <Row label="Billing period" value={data.billing_period} />
        <Row label="Trial days" value={<Count value={data.trial_period_days} />} />
        <Row label="Grace days" value={<Count value={data.grace_period_days} />} />
        {data.description ? (
          <Row label="Description" value={data.description} />
        ) : null}
      </Card>
      <AuditBar entityType="subscription_plan" entityId={data.id} />
    </div>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-[var(--text-primary)]">{value}</span>
    </div>
  );
}
