// admin/apps/portal/app/(tenant-authed)/credit/loans/[id]/_components/RecordRepaymentButton.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  FormField,
  MoneyInput,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
  toast,
} from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import {
  loanRepaymentSchema,
  type LoanRepaymentInput,
  type LoanRepaymentOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface GlAccountOption {
  id: string;
  code: string;
  name: string;
  account_type: string;
}

export function RecordRepaymentButton({
  loanId,
  glAccounts,
}: {
  loanId: string;
  glAccounts: GlAccountOption[];
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const [open, setOpen] = useState(false);
  const [idemKey] = useState(() => crypto.randomUUID());

  const form = useForm<LoanRepaymentInput>({
    resolver: zodResolver(loanRepaymentSchema),
    defaultValues: {
      amount: "",
      payment_account_id: "",
      narration: "",
      idempotency_key: idemKey,
    },
  });

  const mutation = useTypedMutation<LoanRepaymentOut, LoanRepaymentInput>(
    async (vars) => {
      const res = await (
        resources.credit.recordRepayment(loanId, vars) as Promise<{
          data?: LoanRepaymentOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as LoanRepaymentOut;
    },
    {
      onSuccess: () => {
        toast.success("Repayment recorded");
        setOpen(false);
        form.reset({ amount: "", payment_account_id: "", narration: "", idempotency_key: idemKey });
        router.refresh();
      },
      onError: (error) => {
        toast.error("The repayment was not recorded", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <>
      <Button onClick={() => setOpen(true)}>Record repayment</Button>
      <Dialog open={open} onOpenChange={(o) => { if (!o) setOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Record repayment</DialogTitle>
            <DialogDescription>Post a repayment against this loan.</DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
          >
            <FormField control={form.control} name="amount" label="Amount" required
              render={({ field, id, describedBy, invalid }) => (
                <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
                  value={field.value ?? ""} onValueChange={field.onChange}
                  onBlur={field.onBlur} name={field.name} ref={field.ref} />
              )} />
            <FormField control={form.control} name="payment_account_id" label="Payment GL account" required
              render={({ field, id, describedBy, invalid }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
                    <SelectValue placeholder="Choose a GL account…" />
                  </SelectTrigger>
                  <SelectContent>
                    {glAccounts.map((a) => (
                      <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )} />
            <FormField control={form.control} name="narration" label="Narration"
              render={({ field, id, describedBy, invalid }) => (
                <Textarea id={id} rows={2} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <div className="flex gap-3">
              <Button type="submit" disabled={mutation.isPending}>Post repayment</Button>
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
