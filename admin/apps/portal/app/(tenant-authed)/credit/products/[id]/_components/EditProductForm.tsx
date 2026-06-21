// admin/apps/portal/app/(tenant-authed)/credit/products/[id]/_components/EditProductForm.tsx
"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button, FormField, Input, MoneyInput, Textarea, toast } from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import {
  loanProductPatchSchema,
  type LoanProductPatchInput,
  type LoanProductOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function EditProductForm({ product }: { product: LoanProductOut }) {
  const router = useRouter();
  const { resources } = useAuth();

  const form = useForm<LoanProductPatchInput>({
    resolver: zodResolver(loanProductPatchSchema),
    defaultValues: {
      name: product.name,
      description: product.description ?? "",
      penalty_fee_type_code: product.penalty_fee_type_code ?? "",
      write_off_threshold: product.write_off_threshold,
    },
  });

  const mutation = useTypedMutation<LoanProductOut, LoanProductPatchInput>(
    async (vars) => {
      const body: Record<string, unknown> = { ...vars };
      for (const k of ["description", "penalty_fee_type_code"]) {
        if (!body[k]) delete body[k];
      }
      const res = await (
        resources.credit.patchProduct(product.id, body) as Promise<{
          data?: LoanProductOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as LoanProductOut;
    },
    {
      onSuccess: () => {
        toast.success("Product updated");
        router.refresh();
      },
      onError: (error) => {
        toast.error("The product was not updated", {
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
      <FormField control={form.control} name="name" label="Name" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="description" label="Description"
        render={({ field, id, describedBy, invalid }) => (
          <Textarea id={id} rows={2} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="penalty_fee_type_code" label="Penalty fee type code"
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="write_off_threshold" label="Write-off threshold"
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Save changes</Button>
      </div>
    </form>
  );
}
