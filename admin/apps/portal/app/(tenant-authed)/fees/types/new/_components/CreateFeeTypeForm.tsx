// admin/apps/portal/app/(tenant-authed)/fees/types/new/_components/CreateFeeTypeForm.tsx
"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Checkbox,
  FormField,
  Input,
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
  feeTypeSchema,
  type FeeTypeInput,
  type FeeTypeOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface GlAccountOption {
  id: string;
  code: string;
  name: string;
  account_type: string;
}

export function CreateFeeTypeForm({ glAccounts }: { glAccounts: GlAccountOption[] }) {
  const router = useRouter();
  const { resources } = useAuth();

  const form = useForm<FeeTypeInput>({
    resolver: zodResolver(feeTypeSchema),
    defaultValues: {
      code: "",
      name: "",
      description: "",
      applicable_to: "member",
      amount_kind: "fixed",
      amount: "",
      currency: "UGX",
      trigger_kind: "manual",
      event_name: "",
      gl_income_account_code: "",
      gl_receivable_account_code: "",
      requires_collection: false,
    },
  });

  const mutation = useTypedMutation<FeeTypeOut, FeeTypeInput>(
    async (vars) => {
      const body: Record<string, unknown> = { ...vars };
      for (const k of ["description", "event_name"]) {
        if (!body[k]) delete body[k];
      }
      const res = await (
        resources.fees.createType(body) as Promise<{ data?: FeeTypeOut; error?: unknown }>
      );
      if (res.error) throw res.error;
      return res.data as FeeTypeOut;
    },
    {
      onSuccess: () => {
        toast.success("Fee type created");
        router.push("/fees/types");
      },
      onError: (error) => {
        toast.error("The fee type was not created", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const glSelect = (
    field: { value: string; onChange: (v: string) => void },
    id: string,
    describedBy: string | undefined,
    invalid: boolean,
  ) => (
    <Select value={field.value} onValueChange={field.onChange}>
      <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
        <SelectValue placeholder="Choose a GL account…" />
      </SelectTrigger>
      <SelectContent>
        {glAccounts.map((a) => (
          <SelectItem key={a.id} value={a.code}>{a.code} — {a.name}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  return (
    <form
      noValidate
      className="flex max-w-xl flex-col gap-5"
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
    >
      <FormField control={form.control} name="code" label="Code" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="name" label="Name" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="description" label="Description"
        render={({ field, id, describedBy, invalid }) => (
          <Textarea id={id} rows={2} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="applicable_to" label="Applies to" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="member">Member</SelectItem>
              <SelectItem value="savings_account">Savings account</SelectItem>
              <SelectItem value="loan">Loan</SelectItem>
              <SelectItem value="share_account">Share account</SelectItem>
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="amount_kind" label="Charge type" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="fixed">Fixed</SelectItem>
              <SelectItem value="percentage">Percentage</SelectItem>
              <SelectItem value="tiered">Tiered</SelectItem>
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="amount" label="Amount" required
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="currency" label="Currency" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="trigger_kind" label="Trigger" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="event">Event</SelectItem>
              <SelectItem value="schedule">Schedule</SelectItem>
              <SelectItem value="manual">Manual</SelectItem>
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="event_name" label="Event name (optional)"
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="gl_income_account_code" label="Income GL account" required
        render={({ field, id, describedBy, invalid }) => glSelect(field, id, describedBy, invalid)} />
      <FormField control={form.control} name="gl_receivable_account_code" label="Receivable GL account" required
        render={({ field, id, describedBy, invalid }) => glSelect(field, id, describedBy, invalid)} />
      <FormField control={form.control} name="requires_collection" label="Requires collection"
        render={({ field, id }) => (
          <div className="flex items-center gap-2">
            <Checkbox
              id={id}
              checked={field.value ?? false}
              onCheckedChange={(c) => field.onChange(c === true)}
            />
            <span className="text-[var(--text-secondary)]">Requires a separate collection step</span>
          </div>
        )} />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Create fee type</Button>
        <Button type="button" variant="ghost" onClick={() => router.push("/fees/types")}>Cancel</Button>
      </div>
    </form>
  );
}
