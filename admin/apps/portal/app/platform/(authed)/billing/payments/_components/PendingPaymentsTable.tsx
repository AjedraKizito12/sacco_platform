// admin/apps/portal/app/platform/(authed)/billing/payments/_components/PendingPaymentsTable.tsx
"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  DataTable,
  type DataTableProps,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  FormField,
  FormattedDate,
  Money,
  StatusBadge,
  Textarea,
  toast,
  useTableUrlState,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import { paymentRejectSchema, type PaymentRejectInput } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface PendingPaymentRow {
  id: string;
  invoice_id: string;
  invoice_number: string;
  amount: string;
  currency: string;
  payment_method: string;
  recorded_at: string;
  status: string;
}

export function PendingPaymentsTable({
  rows,
  canReject,
}: {
  rows: PendingPaymentRow[];
  canReject: boolean;
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const [rejecting, setRejecting] = useState<PendingPaymentRow | null>(null);

  const form = useForm<PaymentRejectInput>({
    resolver: zodResolver(paymentRejectSchema),
    defaultValues: { reason: "" },
  });

  const mutation = useTypedMutation<unknown, { id: string; reason: string }>(
    async ({ id, reason }) => {
      // resources.billing.rejectPayment is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.billing.rejectPayment(id, { reason }) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [queryKeys.billing.pendingPayments()],
      onSuccess: () => {
        toast.success("Payment rejected");
        setRejecting(null);
        form.reset();
        router.refresh();
      },
      onError: (error) => {
        toast.error("The payment was not rejected", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const columns: DataTableProps<PendingPaymentRow>["columns"] = useMemo(
    () => [
      {
        id: "invoice_number",
        accessorKey: "invoice_number",
        header: "Invoice",
        cell: ({ row }) => (
          <Link
            href={`/platform/billing/invoices/${row.original.invoice_id}`}
            className="font-medium text-[var(--text-link)] hover:underline"
          >
            {row.original.invoice_number}
          </Link>
        ),
      },
      {
        id: "amount",
        accessorKey: "amount",
        header: "Amount",
        cell: ({ row }) => <Money amount={row.original.amount} currency={row.original.currency} />,
      },
      { id: "payment_method", accessorKey: "payment_method", header: "Method" },
      {
        id: "recorded_at",
        accessorKey: "recorded_at",
        header: "Recorded",
        cell: ({ row }) => <FormattedDate value={row.original.recorded_at} />,
      },
      {
        id: "status",
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <StatusBadge entity="payment" status={row.original.status} />,
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) =>
          canReject ? (
            <Button variant="destructive" size="sm" onClick={() => { form.reset(); setRejecting(row.original); }}>
              Reject
            </Button>
          ) : null,
      },
    ],
    [canReject, form],
  );

  const urlState = useTableUrlState({
    defaultSort: { column: "recorded_at", direction: "desc" },
    defaultPageSize: 25,
  });
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <>
      <DataTable<PendingPaymentRow>
        id="billing-pending-payments"
        columns={columns}
        data={pageRows}
        urlState={urlState}
        state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
        emptyState={{
          title: "No payments awaiting confirmation",
          description: "Recorded payments appear here until a second platform user approves or rejects them.",
        }}
      />

      <Dialog open={rejecting !== null} onOpenChange={(o) => { if (!o) setRejecting(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject payment</DialogTitle>
            <DialogDescription>
              {rejecting ? `Reject the payment recorded against ${rejecting.invoice_number}.` : ""}
            </DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={form.handleSubmit(({ reason }) => {
              if (rejecting) mutation.mutate({ id: rejecting.id, reason });
            })}
          >
            <FormField control={form.control} name="reason" label="Reason" required
              helpText="Recorded on the audit log. Minimum 10 characters."
              render={({ field, id, describedBy, invalid }) => (
                <Textarea id={id} rows={3} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <div className="flex gap-3">
              <Button type="submit" variant="destructive" disabled={mutation.isPending}>Reject payment</Button>
              <Button type="button" variant="ghost" onClick={() => setRejecting(null)}>Cancel</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
