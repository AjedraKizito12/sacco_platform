"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Card,
  FormField,
  MakerCheckerConfirmDialog,
  Textarea,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  tenantSuspendSchema,
  type TenantOut,
  type TenantSuspendInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function SuspendTenantForm({ tenant }: { tenant: TenantOut }) {
  const router = useRouter();
  const { resources } = useAuth();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, setPending] = useState<TenantSuspendInput | null>(null);

  const form = useForm<TenantSuspendInput>({
    resolver: zodResolver(tenantSuspendSchema),
    defaultValues: { reason: "" },
  });

  const mutation = useTypedMutation<unknown, TenantSuspendInput>(
    async (vars) => {
      // resources.tenants.suspend is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.tenants.suspend(tenant.id, vars) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [queryKeys.tenants.root(), queryKeys.tenants.detail(tenant.id)],
      onSuccess: () => {
        toast.success("Approval request created", {
          description: "The tenant will be suspended once another platform user approves it.",
        });
        setConfirmOpen(false);
        setPending(null);
        router.push(`/platform/tenants/${tenant.id}`);
      },
      onError: (error) => {
        toast.error("The suspension was not requested", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <>
      <Card className="max-w-xl p-6">
      <form
        noValidate
        className="flex flex-col gap-5"
        onSubmit={form.handleSubmit((values) => {
          setPending(values);
          setConfirmOpen(true);
        })}
      >
        <FormField
          control={form.control}
          name="reason"
          label="Reason"
          required
          helpText="Recorded on the approval request and the audit log. Minimum 10 characters."
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
        <div className="flex gap-3">
          <Button type="submit" variant="destructive" disabled={mutation.isPending}>
            Request Suspension
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => router.push(`/platform/tenants/${tenant.id}`)}
          >
            Cancel
          </Button>
        </div>
      </form>
      </Card>

      <MakerCheckerConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        operationLabel="tenant suspension"
        subjectLabel={tenant.name}
        busy={mutation.isPending}
        onConfirm={() => {
          if (pending) mutation.mutate(pending);
        }}
      />
    </>
  );
}
