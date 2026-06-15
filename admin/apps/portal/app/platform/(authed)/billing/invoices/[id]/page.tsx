// admin/apps/portal/app/platform/(authed)/billing/invoices/[id]/page.tsx
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { AuditBar, Button, Card, FormattedDate, Money, StatusBadge } from "@sacco/ui";
import type { InvoiceDetailOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";

export const metadata = { title: "Invoice" };

export default async function InvoiceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.read");

  const { data } = await (
    resources.billing.getInvoice(id) as Promise<{ data?: InvoiceDetailOut; error?: unknown }>
  );
  if (!data) notFound();

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-[var(--text-h3)] font-semibold">{data.invoice_number}</h1>
        <Button asChild variant="secondary">
          <a href={`/api/billing/invoices/${data.id}/pdf`} target="_blank" rel="noreferrer">
            Download PDF
          </a>
        </Button>
      </div>
      <Card className="flex flex-col gap-3 p-6">
        <Row label="Status" value={<StatusBadge entity="invoice" status={data.status} />} />
        <Row label="Period" value={<><FormattedDate value={data.billing_period_start} /> – <FormattedDate value={data.billing_period_end} /></>} />
        <Row label="Due" value={<FormattedDate value={data.due_at} />} />
        <Row label="Subtotal" value={<Money amount={data.amount_subtotal} currency={data.currency} />} />
        <Row label="Tax" value={<Money amount={data.amount_tax} currency={data.currency} />} />
        <Row label="Total" value={<Money amount={data.amount_total} currency={data.currency} />} />
        <Row label="Paid" value={<Money amount={data.amount_paid} currency={data.currency} />} />
        {data.void_reason ? <Row label="Void reason" value={data.void_reason} /> : null}
      </Card>

      <Card className="flex flex-col gap-2 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Line items</h2>
        <div className="flex flex-col divide-y divide-[var(--border-subtle)]">
          <div className="flex justify-between py-2 text-[13px] text-[var(--text-tertiary)]">
            <span>Description</span>
            <span>Amount</span>
          </div>
          {data.line_items.map((li) => (
            <div key={li.id} className="flex justify-between py-2">
              <span className="text-[var(--text-primary)]">
                {li.description}
                {li.quantity > 1 ? ` × ${li.quantity}` : ""}
              </span>
              <Money amount={li.amount} currency={data.currency} />
            </div>
          ))}
        </div>
      </Card>

      <AuditBar entityType="invoice" entityId={data.id} />
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
