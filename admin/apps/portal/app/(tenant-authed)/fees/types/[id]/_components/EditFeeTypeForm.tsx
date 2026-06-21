// admin/apps/portal/app/(tenant-authed)/fees/types/[id]/_components/EditFeeTypeForm.tsx
"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button, Checkbox, FormField, Input, MoneyInput, Textarea, toast } from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import {
  feeTypePatchSchema,
  type FeeTypePatchInput,
  type FeeTypeOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function EditFeeTypeForm({ feeType }: { feeType: FeeTypeOut }) {
  const router = useRouter();
  const { resources } = useAuth();

  const form = useForm<FeeTypePatchInput>({
    resolver: zodResolver(feeTypePatchSchema),
    defaultValues: {
      name: feeType.name,
      description: feeType.description ?? "",
      amount: feeType.amount,
      is_active: feeType.is_active,
      requires_collection: feeType.requires_collection,
    },
  });

  const mutation = useTypedMutation<FeeTypeOut, FeeTypePatchInput>(
    async (vars) => {
      const body: Record<string, unknown> = { ...vars };
      if (!body["description"]) delete body["description"];
      const res = await (
        resources.fees.patchType(feeType.id, body) as Promise<{
          data?: FeeTypeOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as FeeTypeOut;
    },
    {
      onSuccess: () => {
        toast.success("Fee type updated");
        router.refresh();
      },
      onError: (error) => {
        toast.error("The fee type was not updated", {
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
      <FormField control={form.control} name="amount" label="Amount" required
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="is_active" label="Active"
        render={({ field, id }) => (
          <div className="flex items-center gap-2">
            <Checkbox id={id} checked={field.value ?? false}
              onCheckedChange={(c) => field.onChange(c === true)} />
            <span className="text-[var(--text-secondary)]">Fee type is active</span>
          </div>
        )} />
      <FormField control={form.control} name="requires_collection" label="Requires collection"
        render={({ field, id }) => (
          <div className="flex items-center gap-2">
            <Checkbox id={id} checked={field.value ?? false}
              onCheckedChange={(c) => field.onChange(c === true)} />
            <span className="text-[var(--text-secondary)]">Requires a separate collection step</span>
          </div>
        )} />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Save changes</Button>
      </div>
    </form>
  );
}
