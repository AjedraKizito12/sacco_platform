// admin/apps/portal/app/(tenant-authed)/credit/applications/[id]/_components/DisburseButton.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, ConfirmDialog, toast } from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import type { LoanOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function DisburseButton({ applicationId }: { applicationId: string }) {
  const router = useRouter();
  const { resources } = useAuth();
  const [open, setOpen] = useState(false);
  const [idemKey] = useState(() => crypto.randomUUID());

  const mutation = useTypedMutation<LoanOut, void>(
    async () => {
      const res = await (
        resources.credit.disburse(applicationId, {
          idempotency_key: idemKey,
        }) as Promise<{ data?: LoanOut; error?: unknown }>
      );
      if (res.error) throw res.error;
      return res.data as LoanOut;
    },
    {
      onSuccess: (data) => {
        toast.success("Loan disbursed");
        setOpen(false);
        router.push(`/credit/loans/${data.id}`);
      },
      onError: (error) => {
        toast.error("The loan was not disbursed", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <>
      <Button onClick={() => setOpen(true)}>Disburse</Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Disburse loan"
        description="This creates the loan and posts the disbursement. This cannot be undone."
        confirmLabel="Disburse"
        busy={mutation.isPending}
        onConfirm={() => mutation.mutate()}
      />
    </>
  );
}
