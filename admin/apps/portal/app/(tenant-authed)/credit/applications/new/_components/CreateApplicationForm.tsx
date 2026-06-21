// admin/apps/portal/app/(tenant-authed)/credit/applications/new/_components/CreateApplicationForm.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
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
  Textarea,
  toast,
} from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import {
  loanApplicationSchema,
  type LoanApplicationInput,
  type LoanApplicationOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface MemberOption {
  id: string;
  full_name: string;
  member_number: string;
}
export interface ProductOption {
  id: string;
  name: string;
}

export function CreateApplicationForm({
  members,
  products,
  defaultMemberId,
}: {
  members: MemberOption[];
  products: ProductOption[];
  defaultMemberId?: string;
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const [idemKey] = useState(() => crypto.randomUUID());

  const form = useForm<LoanApplicationInput>({
    resolver: zodResolver(loanApplicationSchema),
    defaultValues: {
      loan_product_id: "",
      member_id: defaultMemberId ?? "",
      requested_amount: "",
      requested_term_periods: "",
      purpose: "",
      disbursement_destination: "member_savings",
      idempotency_key: idemKey,
    },
  });

  const mutation = useTypedMutation<LoanApplicationOut, LoanApplicationInput>(
    async (vars) => {
      const res = await (
        resources.credit.createApplication(vars) as Promise<{
          data?: LoanApplicationOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as LoanApplicationOut;
    },
    {
      onSuccess: (data) => {
        toast.success("Application submitted");
        router.push(`/credit/applications/${data.id}`);
      },
      onError: (error) => {
        toast.error("The application was not submitted", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <form
      noValidate
      className="flex max-w-xl flex-col gap-5"
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
    >
      <FormField control={form.control} name="loan_product_id" label="Product" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose a product…" />
            </SelectTrigger>
            <SelectContent>
              {products.map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="member_id" label="Member" required
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
      <FormField control={form.control} name="requested_amount" label="Requested amount" required
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="requested_term_periods" label="Term (periods)" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} inputMode="numeric" aria-describedby={describedBy}
            aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="purpose" label="Purpose" required
        render={({ field, id, describedBy, invalid }) => (
          <Textarea id={id} rows={2} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="disbursement_destination" label="Disbursement destination" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="member_savings">Member savings</SelectItem>
              <SelectItem value="cash">Cash</SelectItem>
              <SelectItem value="internal_gl">Internal GL</SelectItem>
            </SelectContent>
          </Select>
        )} />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Submit application</Button>
        <Button type="button" variant="ghost" onClick={() => router.push("/credit/applications")}>Cancel</Button>
      </div>
    </form>
  );
}
