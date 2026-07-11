// admin/apps/portal/app/platform/(authed)/billing/invoices/[id]/_components/InvoiceActions.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  FormDialog,
  FormField,
  Input,
  MakerCheckerConfirmDialog,
  MoneyInput,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  PAYMENT_METHOD_OPTIONS,
  invoiceVoidSchema,
  recordPaymentSchema,
  type InvoiceDetailOut,
  type InvoiceVoidInput,
  type RecordPaymentInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function InvoiceActions({
  invoice,
  canRecord,
  canVoid,
}: {
  invoice: InvoiceDetailOut;
  canRecord: boolean;
  canVoid: boolean;
}) {
  const router = useRouter();
  const { resources } = useAuth();

  const [payOpen, setPayOpen] = useState(false);
  const [payConfirm, setPayConfirm] = useState(false);
  const [pendingPayment, setPendingPayment] = useState<RecordPaymentInput | null>(null);
  const [voidOpen, setVoidOpen] = useState(false);
  const [voidConfirm, setVoidConfirm] = useState(false);
  const [pendingVoid, setPendingVoid] = useState<InvoiceVoidInput | null>(null);

  const invalidates = [queryKeys.billing.invoices(), queryKeys.billing.invoice(invoice.id)];

  // Fresh idempotency key per form instance; persists across confirm retries.
  const [idemKey] = useState(() => crypto.randomUUID());
  const payForm = useForm<RecordPaymentInput>({
    resolver: zodResolver(recordPaymentSchema),
    defaultValues: {
      amount: "",
      currency: invoice.currency,
      payment_method: "bank_transfer",
      external_reference: "",
      notes: "",
      idempotency_key: idemKey,
    },
  });

  const voidForm = useForm<InvoiceVoidInput>({
    resolver: zodResolver(invoiceVoidSchema),
    defaultValues: { reason: "" },
  });

  const payMutation = useTypedMutation<unknown, RecordPaymentInput>(
    async (vars) => {
      // resources.billing.recordPayment is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.billing.recordPayment(invoice.id, vars as Record<string, unknown>) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("Payment recorded", {
          description: "It will apply to the invoice once another platform user approves it.",
        });
        setPayConfirm(false);
        setPayOpen(false);
        setPendingPayment(null);
        payForm.reset();
        router.refresh();
      },
      onError: (error) => {
        toast.error("The payment was not recorded", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const voidMutation = useTypedMutation<unknown, InvoiceVoidInput>(
    async (vars) => {
      const res = await (
        resources.billing.voidInvoice(invoice.id, vars as Record<string, unknown>) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("Void requested", {
          description: "The invoice will be voided once another platform user approves it.",
        });
        setVoidConfirm(false);
        setVoidOpen(false);
        setPendingVoid(null);
        voidForm.reset();
        router.refresh();
      },
      onError: (error) => {
        toast.error("The void was not requested", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const payable =
    invoice.status === "issued" || invoice.status === "partial" || invoice.status === "overdue";
  const voidable =
    Number(invoice.amount_paid) === 0 &&
    invoice.status !== "void" &&
    invoice.status !== "paid";

  return (
    <div className="flex items-center gap-2">
      <Button asChild variant="secondary">
        <a href={`/api/billing/invoices/${invoice.id}/pdf`} target="_blank" rel="noreferrer">
          Download PDF
        </a>
      </Button>

      {canRecord && payable ? (
        <Button variant="primary" onClick={() => { payForm.reset({ ...payForm.getValues() }); setPayOpen(true); }}>
          Record payment
        </Button>
      ) : null}
      {canVoid && voidable ? (
        <Button variant="destructive" onClick={() => { voidForm.reset(); setVoidOpen(true); }}>
          Void
        </Button>
      ) : null}

      {/* Record-payment form dialog */}
      {payOpen ? (
        <FormDialog
          title="Record payment"
          description={`Capture an offline payment against ${invoice.invoice_number}. This creates an approval request; the payment applies once another platform user approves it.`}
          onDismiss={() => setPayOpen(false)}
          onSubmit={payForm.handleSubmit((values) => {
            setPendingPayment(values);
            setPayOpen(false);
            setPayConfirm(true);
          })}
          footer={
            <>
              <Button type="button" variant="ghost" onClick={() => setPayOpen(false)}>Cancel</Button>
              <Button type="submit">Record</Button>
            </>
          }
        >
          <FormField control={payForm.control} name="amount" label="Amount" required
            render={({ field, id, describedBy, invalid }) => (
              <MoneyInput id={id} currency={invoice.currency}
                aria-describedby={describedBy} aria-invalid={invalid}
                value={field.value ?? ""} onValueChange={field.onChange}
                onBlur={field.onBlur} name={field.name} ref={field.ref} />
            )} />
          <FormField control={payForm.control} name="payment_method" label="Method" required
            render={({ field, id, describedBy, invalid }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PAYMENT_METHOD_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )} />
          <FormField control={payForm.control} name="external_reference" label="Reference"
            render={({ field, id, describedBy, invalid }) => (
              <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
            )} />
          <FormField control={payForm.control} name="notes" label="Notes"
            render={({ field, id, describedBy, invalid }) => (
              <Textarea id={id} rows={2} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
            )} />
        </FormDialog>
      ) : null}

      <MakerCheckerConfirmDialog
        open={payConfirm}
        onOpenChange={(o) => { setPayConfirm(o); if (!o) setPendingPayment(null); }}
        operationLabel="payment recording"
        subjectLabel={invoice.invoice_number}
        busy={payMutation.isPending}
        onConfirm={() => { if (pendingPayment) payMutation.mutate(pendingPayment); }}
      />

      {/* Void form dialog */}
      {voidOpen ? (
        <FormDialog
          title={`Void ${invoice.invoice_number}`}
          description="Voiding cancels this invoice. This creates an approval request; the invoice is voided once another platform user approves it."
          onDismiss={() => setVoidOpen(false)}
          onSubmit={voidForm.handleSubmit((values) => {
            setPendingVoid(values);
            setVoidOpen(false);
            setVoidConfirm(true);
          })}
          footer={
            <>
              <Button type="button" variant="ghost" onClick={() => setVoidOpen(false)}>Cancel</Button>
              <Button type="submit" variant="destructive">Request void</Button>
            </>
          }
        >
          <FormField control={voidForm.control} name="reason" label="Reason" required
            helpText="Recorded on the approval request and the audit log. Minimum 10 characters."
            render={({ field, id, describedBy, invalid }) => (
              <Textarea id={id} rows={3} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
            )} />
        </FormDialog>
      ) : null}

      <MakerCheckerConfirmDialog
        open={voidConfirm}
        onOpenChange={(o) => { setVoidConfirm(o); if (!o) setPendingVoid(null); }}
        operationLabel="invoice void"
        subjectLabel={invoice.invoice_number}
        busy={voidMutation.isPending}
        onConfirm={() => { if (pendingVoid) voidMutation.mutate(pendingVoid); }}
      />
    </div>
  );
}
