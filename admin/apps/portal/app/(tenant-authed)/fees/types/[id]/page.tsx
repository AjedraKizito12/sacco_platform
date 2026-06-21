// admin/apps/portal/app/(tenant-authed)/fees/types/[id]/page.tsx
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { Card, Money } from "@sacco/ui";
import type { FeeTypeOut } from "@sacco/schemas";
import { getTenantPageContext } from "@/auth/server-page-context";
import { EditFeeTypeForm } from "./_components/EditFeeTypeForm";

export const metadata = { title: "Fee type" };

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-[var(--text-secondary)]">{label}</span>
      <span className="text-right">{children}</span>
    </div>
  );
}

export default async function FeeTypeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { resources } = await getTenantPageContext();
  const { data: feeType } = await (resources.fees.getType(id) as Promise<{
    data?: FeeTypeOut;
    error?: unknown;
  }>);
  if (!feeType) notFound();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">{feeType.name}</h1>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Identity</h2>
        <Row label="Code">{feeType.code}</Row>
        <Row label="Name">{feeType.name}</Row>
        <Row label="Description">{feeType.description ?? "—"}</Row>
        <Row label="Applies to">{feeType.applicable_to}</Row>
      </Card>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Pricing</h2>
        <Row label="Charge type">{feeType.amount_kind}</Row>
        <Row label="Amount"><Money amount={feeType.amount} /></Row>
        <Row label="Currency">{feeType.currency}</Row>
        {feeType.percentage_rate ? (
          <Row label="Percentage rate">{feeType.percentage_rate}</Row>
        ) : null}
        {feeType.percentage_basis ? (
          <Row label="Percentage basis">{feeType.percentage_basis}</Row>
        ) : null}
      </Card>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Trigger</h2>
        <Row label="Trigger kind">{feeType.trigger_kind}</Row>
        <Row label="Event name">{feeType.event_name ?? "—"}</Row>
      </Card>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">GL mapping</h2>
        <Row label="Income account">{feeType.gl_income_account_code}</Row>
        <Row label="Receivable account">{feeType.gl_receivable_account_code}</Row>
      </Card>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Flags</h2>
        <Row label="Active">{feeType.is_active ? "Yes" : "No"}</Row>
        <Row label="Requires collection">{feeType.requires_collection ? "Yes" : "No"}</Row>
      </Card>

      <Card className="flex flex-col gap-3 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Edit</h2>
        <EditFeeTypeForm feeType={feeType} />
      </Card>
    </div>
  );
}
