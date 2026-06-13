"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button, FormField, Input, toast } from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  tenantPatchSchema,
  type TenantOut,
  type TenantPatchInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function EditTenantForm({ tenant }: { tenant: TenantOut }) {
  const router = useRouter();
  const { resources } = useAuth();
  const form = useForm<TenantPatchInput>({
    resolver: zodResolver(tenantPatchSchema),
    defaultValues: { name: tenant.name },
  });

  const mutation = useTypedMutation<unknown, TenantPatchInput>(
    async (vars) => {
      // resources.tenants.patch is typed Promise<never> (as-never paths in
      // tenants.ts); cast to the real { data, error } shape.
      const res = await (
        resources.tenants.patch(tenant.id, vars) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [
        queryKeys.tenants.root(),
        queryKeys.tenants.detail(tenant.id),
      ],
      onSuccess: () => {
        toast.success("Changes saved");
        router.push(`/platform/tenants/${tenant.id}`);
      },
      onError: (error) => {
        toast.error("The tenant was not updated", {
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
      <FormField
        control={form.control}
        name="name"
        label="Name"
        required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )}
      />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Save</Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => router.push(`/platform/tenants/${tenant.id}`)}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
