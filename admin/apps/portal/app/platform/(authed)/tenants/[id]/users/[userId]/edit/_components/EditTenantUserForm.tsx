"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button, Card, Checkbox, FormField, Input, toast } from "@sacco/ui";
import { useTypedMutation, queryKeys } from "@sacco/api-client";
import {
  tenantUserPatchSchema,
  type TenantUserOut,
  type TenantUserPatchInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function EditTenantUserForm({
  tenantId,
  user,
}: {
  tenantId: string;
  user: TenantUserOut;
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const detailHref = `/platform/tenants/${tenantId}/users/${user.id}`;

  const form = useForm<TenantUserPatchInput>({
    resolver: zodResolver(tenantUserPatchSchema),
    defaultValues: {
      full_name: user.full_name,
      is_active: user.is_active,
      is_admin: user.is_admin,
    },
  });

  // Tenant-user PATCH is a direct operation (no maker-checker).
  const mutation = useTypedMutation<unknown, TenantUserPatchInput>(
    async (vars) => {
      const body = vars as { full_name?: string; is_active?: boolean; is_admin?: boolean };
      const res = await (
        resources.tenants.patchUser(tenantId, user.id, body) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [queryKeys.tenants.users(tenantId)],
      onSuccess: () => {
        toast.success("Tenant user updated");
        router.push(detailHref);
      },
      onError: (error) => {
        toast.error("The user was not updated", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <Card className="max-w-xl p-6">
    <form
      noValidate
      className="flex flex-col gap-5"
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
    >
      <FormField
        control={form.control}
        name="full_name"
        label="Full name"
        required
        render={({ field, id, describedBy, invalid }) => (
          <Input
            id={id}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            value={field.value ?? ""}
            onChange={field.onChange}
            onBlur={field.onBlur}
            name={field.name}
            ref={field.ref}
          />
        )}
      />
      <FormField
        control={form.control}
        name="is_active"
        label="Active"
        helpText="Inactive users cannot sign in."
        render={({ field, id, describedBy }) => (
          <Checkbox
            id={id}
            aria-describedby={describedBy}
            checked={field.value ?? false}
            onCheckedChange={(v) => field.onChange(Boolean(v))}
          />
        )}
      />
      <FormField
        control={form.control}
        name="is_admin"
        label="Tenant admin"
        helpText="Admins can manage their SACCO's configuration and other users."
        render={({ field, id, describedBy }) => (
          <Checkbox
            id={id}
            aria-describedby={describedBy}
            checked={field.value ?? false}
            onCheckedChange={(v) => field.onChange(Boolean(v))}
          />
        )}
      />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Save changes</Button>
        <Button type="button" variant="ghost" onClick={() => router.push(detailHref)}>
          Cancel
        </Button>
      </div>
    </form>
    </Card>
  );
}
