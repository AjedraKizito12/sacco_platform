// admin/apps/portal/app/(tenant-authed)/credit/payroll/[id]/_components/RejectPayrollBatchButton.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, ConfirmDialog, toast } from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import type { PayrollBatchOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function RejectPayrollBatchButton({
  batchId,
  status,
}: {
  batchId: string;
  status: string;
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const [open, setOpen] = useState(false);

  const mutation = useTypedMutation<PayrollBatchOut, void>(
    async () => {
      const res = await (
        resources.credit.rejectPayrollBatch(batchId, {}) as Promise<{
          data?: PayrollBatchOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as PayrollBatchOut;
    },
    {
      onSuccess: () => {
        toast.success("Batch rejected");
        setOpen(false);
        router.refresh();
      },
      onError: (error) => {
        toast.error("The batch was not rejected", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  if (status !== "pending_review") return null;

  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>Reject batch</Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Reject payroll batch"
        description="This rejects the batch. This cannot be undone."
        confirmLabel="Reject"
        destructive
        busy={mutation.isPending}
        onConfirm={() => mutation.mutate()}
      />
    </>
  );
}
