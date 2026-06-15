"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button, ConfirmDialog, toast } from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import type { TenantOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function TenantActions({
  tenant,
  canWrite,
  canImpersonate,
  canAssignPlan,
}: {
  tenant: TenantOut;
  canWrite: boolean;
  canImpersonate: boolean;
  canAssignPlan: boolean;
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const [reactivateOpen, setReactivateOpen] = useState(false);

  const reactivation = useTypedMutation<unknown, void>(
    async () => {
      // resources.tenants.reactivate is typed Promise<never>; cast to the real shape.
      const res = await (
        resources.tenants.reactivate(tenant.id) as Promise<{
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
        toast.success("Tenant reactivated");
        setReactivateOpen(false);
        router.refresh();
      },
      onError: (error) => {
        toast.error("The tenant was not reactivated", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const isSuspended = tenant.status === "suspended";

  return (
    <div className="flex items-center gap-2">
      {canImpersonate ? (
        <Button asChild variant="secondary">
          <Link href={`/platform/tenants/${tenant.id}/impersonate`}>Impersonate</Link>
        </Button>
      ) : null}
      {canAssignPlan ? (
        <Button asChild variant="secondary">
          <Link href={`/platform/tenants/${tenant.id}/assign-plan`}>Assign plan</Link>
        </Button>
      ) : null}
      {canWrite && !isSuspended ? (
        <Button asChild variant="secondary">
          <Link href={`/platform/tenants/${tenant.id}/edit`}>Edit</Link>
        </Button>
      ) : null}
      {canWrite && !isSuspended ? (
        <Button asChild variant="destructive">
          <Link href={`/platform/tenants/${tenant.id}/suspend`}>Suspend</Link>
        </Button>
      ) : null}
      {canWrite && isSuspended ? (
        <Button variant="primary" onClick={() => setReactivateOpen(true)}>
          Reactivate
        </Button>
      ) : null}

      <ConfirmDialog
        open={reactivateOpen}
        onOpenChange={setReactivateOpen}
        title={`Reactivate ${tenant.name}?`}
        description="This restores tenant access immediately. No approval is required."
        confirmLabel="Reactivate tenant"
        busy={reactivation.isPending}
        onConfirm={() => reactivation.mutate()}
      />
    </div>
  );
}
