// admin/apps/portal/app/platform/(authed)/billing/payments/page.tsx
import { Card } from "@sacco/ui";
import type { InvoiceOut, PaymentOut } from "@sacco/schemas";
import {
  getPlatformPageContext,
  requirePlatformPermission,
} from "@/auth/server-page-context";
import { userHasPermission } from "@/auth/permissions";
import { BillingTabs } from "../_components/BillingTabs";
import {
  PendingPaymentsTable,
  type PendingPaymentRow,
} from "./_components/PendingPaymentsTable";

export const metadata = { title: "Payments" };

export default async function BillingPaymentsPage() {
  const { user, resources } = await getPlatformPageContext();
  requirePlatformPermission(user, "billing.read");

  const [{ data: payments }, { data: invoices }] = await Promise.all([
    resources.billing.listPendingPayments() as Promise<{ data?: PaymentOut[]; error?: unknown }>,
    resources.billing.listInvoices() as Promise<{ data?: InvoiceOut[]; error?: unknown }>,
  ]);

  const invoiceNumber = new Map((invoices ?? []).map((inv) => [inv.id, inv.invoice_number]));
  const rows: PendingPaymentRow[] = (payments ?? []).map((p) => ({
    id: p.id,
    invoice_id: p.invoice_id,
    invoice_number: invoiceNumber.get(p.invoice_id) ?? p.invoice_id,
    amount: p.amount,
    currency: p.currency,
    payment_method: p.payment_method,
    recorded_at: p.recorded_at,
    status: p.status,
  }));

  const canReject = userHasPermission(user, "billing.write");

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-[var(--text-h3)] font-semibold">Billing</h1>
      <BillingTabs />
      <p className="text-[13px] text-[var(--text-secondary)]">
        Approving a payment is done from the Approvals inbox. Rejecting is available here.
      </p>
      <Card className="p-0">
        <PendingPaymentsTable rows={rows} canReject={canReject} />
      </Card>
    </div>
  );
}
