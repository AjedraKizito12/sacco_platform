"use client";

import { useState } from "react";
import { Button, MakerCheckerConfirmDialog, toast } from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import type { TenantOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

/**
 * Maker-checker CTA on a failed tenant. The backend endpoint submits a
 * tenant.retry_provisioning approval request (quorum 1) — it does not retry
 * directly. Contract K: the button is labeled "Request X", not "X".
 */
export function RetryProvisioningButton({ tenant }: { tenant: TenantOut }) {
  const { resources } = useAuth();
  const [confirmOpen, setConfirmOpen] = useState(false);

  const mutation = useTypedMutation<unknown, void>(
    async () => {
      // resources.tenants.retryProvisioning is typed Promise<never>
      // (as-never paths in tenants.ts); cast to the real { data, error } shape.
      const res = await (
        resources.tenants.retryProvisioning(tenant.id) as Promise<{
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
          description:
            "Provisioning will retry once another platform user approves it.",
        });
        setConfirmOpen(false);
      },
      onError: (error) => {
        toast.error("The retry was not requested", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <>
      <Button variant="secondary" onClick={() => setConfirmOpen(true)}>
        Request Provisioning Retry
      </Button>
      <MakerCheckerConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        operationLabel="provisioning retry"
        subjectLabel={tenant.slug}
        busy={mutation.isPending}
        onConfirm={() => mutation.mutate()}
      />
    </>
  );
}
