// admin/apps/portal/app/(tenant-authed)/credit/payroll/new/_components/CreatePayrollBatchForm.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  FormDialog,
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
  payrollBatchSchema,
  type PayrollBatchInput,
  type PayrollBatchOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface MemberOption {
  id: string;
  full_name: string;
  member_number: string;
}
export interface GlAccountOption {
  id: string;
  code: string;
  name: string;
  account_type: string;
}

export function CreatePayrollBatchForm({
  members,
  glAccounts,
}: {
  members: MemberOption[];
  glAccounts: GlAccountOption[];
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const [idemKey] = useState(() => crypto.randomUUID());

  const form = useForm<PayrollBatchInput>({
    resolver: zodResolver(payrollBatchSchema),
    defaultValues: {
      rows: [{ member_id: "", amount: "" }],
      clearing_account_id: "",
      idempotency_key: idemKey,
    },
  });
  const { fields, append, remove } = useFieldArray({ control: form.control, name: "rows" });

  const mutation = useTypedMutation<PayrollBatchOut, PayrollBatchInput>(
    async (vars) => {
      const res = await (
        resources.credit.createPayrollBatch(vars) as Promise<{
          data?: PayrollBatchOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as PayrollBatchOut;
    },
    {
      onSuccess: (data) => {
        toast.success("Batch created");
        router.push(`/credit/payroll/${data.id}`);
      },
      onError: (error) => {
        toast.error("The batch was not created", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <FormDialog
      title="New payroll batch"
      description="Capture per-member repayment amounts to apply as a batch."
      className="max-w-2xl"
      onDismiss={() => router.back()}
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={() => router.back()}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
            Create batch
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {fields.map((f, i) => (
          <div key={f.id} className="flex items-end gap-3">
            <div className="flex-1">
              <FormField control={form.control} name={`rows.${i}.member_id`} label="Member" required
                render={({ field, id, describedBy, invalid }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
                      <SelectValue placeholder="Choose a member…" />
                    </SelectTrigger>
                    <SelectContent>
                      {members.map((m) => (
                        <SelectItem key={m.id} value={m.id}>{m.full_name} ({m.member_number})</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )} />
            </div>
            <div className="flex-1">
              <FormField control={form.control} name={`rows.${i}.amount`} label="Amount" required
                render={({ field, id, describedBy, invalid }) => (
                  <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
                    value={field.value ?? ""} onValueChange={field.onChange}
                    onBlur={field.onBlur} name={field.name} ref={field.ref} />
                )} />
            </div>
            <Button
              type="button"
              variant="ghost"
              disabled={fields.length === 1}
              onClick={() => remove(i)}
            >
              Remove
            </Button>
          </div>
        ))}
        <div>
          <Button type="button" variant="secondary" onClick={() => append({ member_id: "", amount: "" })}>
            Add row
          </Button>
        </div>
      </div>

      <FormField control={form.control} name="clearing_account_id" label="Clearing account" required
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

    </FormDialog>
  );
}
