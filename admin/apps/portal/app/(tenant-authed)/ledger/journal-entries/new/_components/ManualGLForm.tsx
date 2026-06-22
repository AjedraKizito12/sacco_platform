// admin/apps/portal/app/(tenant-authed)/ledger/journal-entries/new/_components/ManualGLForm.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  FormField,
  Input,
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
  manualJournalEntrySchema,
  type ManualJournalEntryInput,
  type ManualGLSubmitOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface AccountOption {
  id: string;
  code: string;
  name: string;
}

const emptyLine = {
  account_id: "",
  debit_amount: "0",
  credit_amount: "0",
  description: "",
};

export function ManualGLForm({ accounts }: { accounts: AccountOption[] }) {
  const router = useRouter();
  const { resources } = useAuth();
  const [idemKey] = useState(() => crypto.randomUUID());

  const form = useForm<ManualJournalEntryInput>({
    resolver: zodResolver(manualJournalEntrySchema),
    defaultValues: {
      reference: "",
      description: "",
      idempotency_key: idemKey,
      lines: [{ ...emptyLine }, { ...emptyLine }],
    },
  });
  const { fields, append, remove } = useFieldArray({ control: form.control, name: "lines" });

  const mutation = useTypedMutation<ManualGLSubmitOut, ManualJournalEntryInput>(
    async (vars) => {
      const res = await (
        resources.ledger.submitJournalEntry(vars) as Promise<{
          data?: ManualGLSubmitOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as ManualGLSubmitOut;
    },
    {
      onSuccess: () => {
        toast.success("GL entry submitted — pending approval");
        router.push("/ledger/journal-entries");
      },
      onError: (error) => {
        toast.error("The GL entry was not submitted", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const linesError =
    form.formState.errors.lines?.root?.message ?? form.formState.errors.lines?.message;

  return (
    <form
      noValidate
      className="flex max-w-2xl flex-col gap-5"
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
    >
      <p className="text-[var(--text-sm)] text-[var(--text-secondary)]">
        Posting a manual GL entry creates a maker-checker approval (quorum applies); it
        posts once approved.
      </p>

      <FormField control={form.control} name="reference" label="Reference" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="description" label="Description" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />

      <div className="flex flex-col gap-4">
        {fields.map((f, i) => (
          <div key={f.id} className="flex items-end gap-3">
            <div className="flex-1">
              <FormField control={form.control} name={`lines.${i}.account_id`} label={`Account ${i + 1}`} required
                render={({ field, id, describedBy, invalid }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
                      <SelectValue placeholder="Choose an account…" />
                    </SelectTrigger>
                    <SelectContent>
                      {accounts.map((a) => (
                        <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )} />
            </div>
            <div className="w-32">
              <FormField control={form.control} name={`lines.${i}.debit_amount`} label={`Debit ${i + 1}`}
                render={({ field, id, describedBy, invalid }) => (
                  <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
                    value={field.value ?? ""} onValueChange={field.onChange}
                    onBlur={field.onBlur} name={field.name} ref={field.ref} />
                )} />
            </div>
            <div className="w-32">
              <FormField control={form.control} name={`lines.${i}.credit_amount`} label={`Credit ${i + 1}`}
                render={({ field, id, describedBy, invalid }) => (
                  <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
                    value={field.value ?? ""} onValueChange={field.onChange}
                    onBlur={field.onBlur} name={field.name} ref={field.ref} />
                )} />
            </div>
            <Button
              type="button"
              variant="ghost"
              disabled={fields.length === 2}
              onClick={() => remove(i)}
            >
              Remove
            </Button>
          </div>
        ))}
        <div>
          <Button type="button" variant="secondary" onClick={() => append({ ...emptyLine })}>
            Add line
          </Button>
        </div>
        {linesError ? (
          <p className="text-[var(--text-sm)] text-[var(--text-danger)]">{linesError}</p>
        ) : null}
      </div>

      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Submit GL entry</Button>
        <Button type="button" variant="ghost" onClick={() => router.push("/ledger/journal-entries")}>Cancel</Button>
      </div>
    </form>
  );
}
