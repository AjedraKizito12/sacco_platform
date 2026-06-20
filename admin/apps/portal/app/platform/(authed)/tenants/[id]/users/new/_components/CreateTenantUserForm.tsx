"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button, Checkbox, FormField, Input, toast } from "@sacco/ui";
import { useTypedMutation, queryKeys } from "@sacco/api-client";
import {
  tenantUserCreateSchema,
  type TenantUserCreateInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";
import { OneTimeModal } from "@/components/OneTimeModal";

interface CreatedToken {
  token: string;
  ttlSeconds: number;
}

export function CreateTenantUserForm({ tenantId }: { tenantId: string }) {
  const router = useRouter();
  const { resources } = useAuth();
  const [created, setCreated] = useState<CreatedToken | null>(null);

  const form = useForm<TenantUserCreateInput>({
    resolver: zodResolver(tenantUserCreateSchema),
    defaultValues: { email: "", full_name: "", is_admin: false },
  });

  const mutation = useTypedMutation<
    { password_reset_token: string; password_reset_expires_in: number },
    TenantUserCreateInput
  >(
    async (vars) => {
      const res = await (
        resources.tenants.createUser(tenantId, vars) as Promise<{
          data?: { password_reset_token: string; password_reset_expires_in: number };
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data!;
    },
    {
      invalidates: [queryKeys.tenants.users(tenantId)],
      onSuccess: (data) => {
        setCreated({
          token: data.password_reset_token,
          ttlSeconds: data.password_reset_expires_in,
        });
      },
      onError: (error) => {
        toast.error("The user was not created", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <>
      <form
        noValidate
        className="flex max-w-xl flex-col gap-5"
        onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
      >
        <FormField
          control={form.control}
          name="email"
          label="Email"
          required
          render={({ field, id, describedBy, invalid }) => (
            <Input id={id} type="email" aria-describedby={describedBy} aria-invalid={invalid} {...field} />
          )}
        />
        <FormField
          control={form.control}
          name="full_name"
          label="Full name"
          required
          render={({ field, id, describedBy, invalid }) => (
            <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
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
              checked={field.value}
              onCheckedChange={(v) => field.onChange(Boolean(v))}
            />
          )}
        />
        <div className="flex gap-3">
          <Button type="submit" disabled={mutation.isPending}>Create user</Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => router.push(`/platform/tenants/${tenantId}/users`)}
          >
            Cancel
          </Button>
        </div>
      </form>

      <OneTimeModal
        open={created !== null}
        onAcknowledge={() => {
          setCreated(null);
          toast.success("Tenant user created");
          router.push(`/platform/tenants/${tenantId}/users`);
        }}
        title="User created"
        description="Share this one-time password-reset link with the user out of band. It won't be shown again."
        payload={created?.token ?? ""}
        payloadLabel="Password reset token"
        warningCopy={`Valid for ${Math.round((created?.ttlSeconds ?? 0) / 3600)} hours.`}
      />
    </>
  );
}
