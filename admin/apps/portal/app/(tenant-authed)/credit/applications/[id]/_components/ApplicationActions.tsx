// admin/apps/portal/app/(tenant-authed)/credit/applications/[id]/_components/ApplicationActions.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  ConfirmDialog,
  FormDialog,
  FormField,
  Textarea,
  toast,
} from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import {
  loanApplicationRejectSchema,
  type LoanApplicationRejectInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function ApplicationActions({ applicationId }: { applicationId: string }) {
  const router = useRouter();
  const { resources } = useAuth();

  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [withdrawOpen, setWithdrawOpen] = useState(false);

  const rejectForm = useForm<LoanApplicationRejectInput>({
    resolver: zodResolver(loanApplicationRejectSchema),
    defaultValues: { reason: "" },
  });

  const approveMutation = useTypedMutation<unknown, Record<string, never>>(
    async () => {
      const res = await (
        resources.credit.approveApplication(applicationId, {}) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      onSuccess: () => {
        toast.success("Application approved");
        setApproveOpen(false);
        router.refresh();
      },
      onError: (error) => {
        toast.error("The application was not approved", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const rejectMutation = useTypedMutation<unknown, LoanApplicationRejectInput>(
    async (vars) => {
      const res = await (
        resources.credit.rejectApplication(applicationId, vars) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      onSuccess: () => {
        toast.success("Application rejected");
        setRejectOpen(false);
        rejectForm.reset({ reason: "" });
        router.refresh();
      },
      onError: (error) => {
        toast.error("The application was not rejected", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const withdrawMutation = useTypedMutation<unknown, Record<string, never>>(
    async () => {
      const res = await (
        resources.credit.withdrawApplication(applicationId, {}) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      onSuccess: () => {
        toast.success("Application withdrawn");
        setWithdrawOpen(false);
        router.refresh();
      },
      onError: (error) => {
        toast.error("The application was not withdrawn", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <div className="flex items-center gap-2">
      <Button onClick={() => setApproveOpen(true)}>Approve</Button>
      <Button variant="secondary" onClick={() => setRejectOpen(true)}>Reject</Button>
      <Button variant="ghost" onClick={() => setWithdrawOpen(true)}>Withdraw</Button>

      <ConfirmDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        title="Approve loan application"
        description="This records your approval. When the required number of approvals is reached, the application is approved."
        confirmLabel="Approve"
        busy={approveMutation.isPending}
        onConfirm={() => approveMutation.mutate({})}
      />

      <ConfirmDialog
        open={withdrawOpen}
        onOpenChange={setWithdrawOpen}
        title="Withdraw application"
        description="This withdraws the pending application. This cannot be undone."
        confirmLabel="Withdraw"
        destructive
        busy={withdrawMutation.isPending}
        onConfirm={() => withdrawMutation.mutate({})}
      />

      {rejectOpen ? (
        <FormDialog
          title="Reject application"
          description="Record a reason for rejecting this application."
          onDismiss={() => setRejectOpen(false)}
          onSubmit={rejectForm.handleSubmit((values) => rejectMutation.mutate(values))}
          footer={
            <>
              <Button type="button" variant="ghost" onClick={() => setRejectOpen(false)}>Cancel</Button>
              <Button type="submit" variant="destructive" disabled={rejectMutation.isPending}>
                Reject application
              </Button>
            </>
          }
        >
          <FormField control={rejectForm.control} name="reason" label="Reason" required
            render={({ field, id, describedBy, invalid }) => (
              <Textarea id={id} rows={3} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
            )} />
        </FormDialog>
      ) : null}
    </div>
  );
}
