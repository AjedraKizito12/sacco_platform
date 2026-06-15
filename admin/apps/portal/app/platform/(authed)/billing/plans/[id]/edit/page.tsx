// admin/apps/portal/app/platform/(authed)/billing/plans/[id]/edit/page.tsx
import { notFound } from "next/navigation";
import type { SubscriptionPlanOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { EditPlanForm } from "./_components/EditPlanForm";

export const metadata = { title: "Edit Plan" };

export default async function EditPlanPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.write");

  const { data } = await (
    resources.billing.getPlan(id) as Promise<{
      data?: SubscriptionPlanOut;
      error?: unknown;
    }>
  );
  if (!data) notFound();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Edit {data.name}</h1>
      <EditPlanForm plan={data} />
    </div>
  );
}
