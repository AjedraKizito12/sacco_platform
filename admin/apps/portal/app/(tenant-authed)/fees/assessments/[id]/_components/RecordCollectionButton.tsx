// admin/apps/portal/app/(tenant-authed)/fees/assessments/[id]/_components/RecordCollectionButton.tsx
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
  toast,
} from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import {
  feeCollectionSchema,
  type FeeCollectionInput,
  type FeeCollectionOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface GlAccountOption {
  id: string;
  code: string;
  name: string;
  account_type: string;
}

const TERMINAL = new Set(["paid", "waived", "cancelled"]);

export function RecordCollectionButton({
  assessmentId,
  status,
  glAccounts,
}: {
  assessmentId: string;
  status: string;
  glAccounts: GlAccountOption[];
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const [open, setOpen] = useState(false);
  const [idemKey] = useState(() => crypto.randomUUID());

  const form = useForm<FeeCollectionInput>({
    resolver: zodResolver(feeCollectionSchema),
    defaultValues: {
      fee_assessment_id: assessmentId,
      amount: "",
      method: "cash",
      contra_account_id: "",
      idempotency_key: idemKey,
    },
  });

  const mutation = useTypedMutation<FeeCollectionOut, FeeCollectionInput>(
    async (vars) => {
      const res = await (
        resources.fees.recordCollection(vars) as Promise<{
          data?: FeeCollectionOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as FeeCollectionOut;
    },
    {
      onSuccess: () => {
        toast.success("Collection recorded");
        setOpen(false);
        form.reset({
          fee_assessment_id: assessmentId,
          amount: "",
          method: "cash",
          contra_account_id: "",
          idempotency_key: idemKey,
        });
        router.refresh();
      },
      onError: (error) => {
        toast.error("The collection was not recorded", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  if (TERMINAL.has(status)) return null;

  return (
    <>
      <Button onClick={() => setOpen(true)}>Record collection</Button>
      <Dialog open={open} onOpenChange={(o) => { if (!o) setOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Record collection</DialogTitle>
            <DialogDescription>Record a payment against this assessment.</DialogDescription>
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
            <FormField control={form.control} name="method" label="Method" required
              render={({ field, id, describedBy, invalid }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
                    <SelectValue placeholder="Choose…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="journal_voucher">Journal voucher</SelectItem>
                  </SelectContent>
                </Select>
              )} />
            <FormField control={form.control} name="contra_account_id" label="Contra GL account" required
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
            <div className="flex gap-3">
              <Button type="submit" disabled={mutation.isPending}>Record</Button>
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
