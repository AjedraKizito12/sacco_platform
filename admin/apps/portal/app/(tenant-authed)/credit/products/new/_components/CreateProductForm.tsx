// admin/apps/portal/app/(tenant-authed)/credit/products/new/_components/CreateProductForm.tsx
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
  PercentageInput,
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
  loanProductSchema,
  type LoanProductInput,
  type LoanProductOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface GlAccountOption {
  id: string;
  code: string;
  name: string;
  account_type: string;
}

const DESTS = [
  { value: "member_savings", label: "Member savings" },
  { value: "cash", label: "Cash" },
  { value: "internal_gl", label: "Internal GL" },
] as const;

export function CreateProductForm({ glAccounts }: { glAccounts: GlAccountOption[] }) {
  const router = useRouter();
  const { resources } = useAuth();

  const form = useForm<LoanProductInput>({
    resolver: zodResolver(loanProductSchema),
    defaultValues: {
      name: "",
      description: "",
      interest_method: "reducing_balance",
      annual_interest_rate: "",
      repayment_frequency: "monthly",
      max_term_periods: "",
      min_amount: "",
      max_amount: "",
      required_approvals: "1",
      repayment_allocation: "INTEREST_PRINCIPAL",
      disbursement_destinations: [],
      gl_principal_receivable_code: "",
      gl_interest_receivable_code: "",
      gl_interest_income_code: "",
      gl_loan_loss_expense_code: "",
      penalty_fee_type_code: "",
      write_off_threshold: "",
    },
  });

  const mutation = useTypedMutation<LoanProductOut, LoanProductInput>(
    async (vars) => {
      const body: Record<string, unknown> = { ...vars };
      for (const k of [
        "description",
        "gl_loan_loss_expense_code",
        "penalty_fee_type_code",
        "write_off_threshold",
      ]) {
        if (!body[k]) delete body[k];
      }
      const res = await (
        resources.credit.createProduct(body) as Promise<{
          data?: LoanProductOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as LoanProductOut;
    },
    {
      onSuccess: () => {
        toast.success("Product created");
        router.push("/credit");
      },
      onError: (error) => {
        toast.error("The product was not created", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const glSelect = (
    field: { value: string | undefined; onChange: (v: string) => void },
    id: string,
    describedBy: string | undefined,
    invalid: boolean,
  ) => (
    <Select value={field.value ?? ""} onValueChange={field.onChange}>
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
      <FormField control={form.control} name="name" label="Name" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="description" label="Description"
        render={({ field, id, describedBy, invalid }) => (
          <Textarea id={id} rows={2} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="interest_method" label="Interest method" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="flat">Flat</SelectItem>
              <SelectItem value="reducing_balance">Reducing balance</SelectItem>
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="annual_interest_rate" label="Annual interest rate (%)" required
        render={({ field, id, describedBy, invalid }) => (
          <PercentageInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="repayment_frequency" label="Repayment frequency" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="weekly">Weekly</SelectItem>
              <SelectItem value="biweekly">Biweekly</SelectItem>
              <SelectItem value="monthly">Monthly</SelectItem>
              <SelectItem value="quarterly">Quarterly</SelectItem>
              <SelectItem value="lump_sum">Lump sum</SelectItem>
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="max_term_periods" label="Max term (periods)" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} inputMode="numeric" aria-describedby={describedBy}
            aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="min_amount" label="Minimum amount" required
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="max_amount" label="Maximum amount" required
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="required_approvals" label="Required approvals" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} inputMode="numeric" aria-describedby={describedBy}
            aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="repayment_allocation" label="Repayment allocation" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="INTEREST_PRINCIPAL">Interest, then principal</SelectItem>
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="disbursement_destinations" label="Disbursement destinations" required
        render={({ field }) => (
          <div className="flex flex-col gap-2">
            {DESTS.map((d) => {
              const current = (field.value ?? []) as string[];
              const checked = current.includes(d.value);
              return (
                <label key={d.value} className="flex items-center gap-2">
                  <Checkbox
                    checked={checked}
                    onCheckedChange={(c) => {
                      const next = new Set<string>(current);
                      if (c) next.add(d.value);
                      else next.delete(d.value);
                      field.onChange([...next]);
                    }}
                  />
                  <span>{d.label}</span>
                </label>
              );
            })}
          </div>
        )} />
      <FormField control={form.control} name="gl_principal_receivable_code" label="Principal receivable GL" required
        render={({ field, id, describedBy, invalid }) => glSelect(field, id, describedBy, invalid)} />
      <FormField control={form.control} name="gl_interest_receivable_code" label="Interest receivable GL" required
        render={({ field, id, describedBy, invalid }) => glSelect(field, id, describedBy, invalid)} />
      <FormField control={form.control} name="gl_interest_income_code" label="Interest income GL" required
        render={({ field, id, describedBy, invalid }) => glSelect(field, id, describedBy, invalid)} />
      <FormField control={form.control} name="gl_loan_loss_expense_code" label="Loan-loss expense GL (optional)"
        render={({ field, id, describedBy, invalid }) => glSelect(field, id, describedBy, invalid)} />
      <FormField control={form.control} name="penalty_fee_type_code" label="Penalty fee type code (optional)"
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="write_off_threshold" label="Write-off threshold (optional)"
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Create product</Button>
        <Button type="button" variant="ghost" onClick={() => router.push("/credit")}>Cancel</Button>
      </div>
    </form>
  );
}
