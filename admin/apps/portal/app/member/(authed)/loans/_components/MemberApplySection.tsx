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
  Money,
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
  memberLoanApplySchema,
  type LoanApplicationOut,
  type MemberLoanApplyInput,
  type MemberLoanProductOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function MemberApplySection({
  products,
}: {
  products: MemberLoanProductOut[];
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const [open, setOpen] = useState(false);

  const form = useForm<MemberLoanApplyInput>({
    resolver: zodResolver(memberLoanApplySchema),
    defaultValues: {
      loan_product_id: "",
      requested_amount: "",
      requested_term_periods: "",
      purpose: "",
    },
  });

  const selectedId = form.watch("loan_product_id");
  const selected = products.find((p) => p.id === selectedId);

  const mutation = useTypedMutation<LoanApplicationOut, MemberLoanApplyInput>(
    async (input) => {
      const res = await (resources.member.applyForLoan(
        input as unknown as Record<string, unknown>,
      ) as Promise<{ data?: LoanApplicationOut; error?: unknown }>);
      if (res.error || !res.data) throw res.error ?? new Error("Empty response");
      return res.data;
    },
    {
      invalidates: [queryKeys.member.loanApplications()],
      onSuccess: () => {
        toast.success("Application submitted", {
          description: "SACCO staff will review your application.",
        });
        setOpen(false);
        form.reset();
        router.refresh();
      },
      onError: (error) => {
        toast.error("Your application was not submitted", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  if (products.length === 0) return null;

  return (
    <>
      <Button onClick={() => setOpen(true)}>Apply for a loan</Button>
      {open ? (
        <FormDialog
          title="Apply for a loan"
          description="Your application is reviewed and approved by SACCO staff."
          onDismiss={() => setOpen(false)}
          onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
          footer={
            <>
              <Button
                type="button"
                variant="secondary"
                onClick={() => setOpen(false)}
                disabled={mutation.isPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={mutation.isPending}>
                Submit application
              </Button>
            </>
          }
        >
          <FormField
            control={form.control}
            name="loan_product_id"
            label="Product"
            required
            render={({ field, id, describedBy, invalid }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
                  <SelectValue placeholder="Choose a product…" />
                </SelectTrigger>
                <SelectContent>
                  {products.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          {selected ? (
            <p className="text-[var(--text-secondary)]">
              <Money amount={selected.min_amount} /> –{" "}
              <Money amount={selected.max_amount} /> · up to{" "}
              {selected.max_term_periods} {selected.repayment_frequency} periods
            </p>
          ) : null}
          <FormField
            control={form.control}
            name="requested_amount"
            label="Amount"
            required
            render={({ field, id, describedBy, invalid }) => (
              <MoneyInput
                id={id}
                aria-describedby={describedBy}
                aria-invalid={invalid}
                value={field.value ?? ""}
                onValueChange={field.onChange}
                onBlur={field.onBlur}
                name={field.name}
                ref={field.ref}
              />
            )}
          />
          <FormField
            control={form.control}
            name="requested_term_periods"
            label="Term (periods)"
            required
            render={({ field, id, describedBy, invalid }) => (
              <Input
                id={id}
                inputMode="numeric"
                aria-describedby={describedBy}
                aria-invalid={invalid}
                {...field}
              />
            )}
          />
          <FormField
            control={form.control}
            name="purpose"
            label="Purpose"
            required
            render={({ field, id, describedBy, invalid }) => (
              <Textarea
                id={id}
                rows={3}
                aria-describedby={describedBy}
                aria-invalid={invalid}
                {...field}
              />
            )}
          />
        </FormDialog>
      ) : null}
    </>
  );
}
