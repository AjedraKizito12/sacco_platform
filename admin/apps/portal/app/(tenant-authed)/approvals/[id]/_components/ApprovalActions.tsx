"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  FormField,
  Textarea,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  approveActionSchema,
  rejectActionSchema,
  type ApproveActionInput,
  type RejectActionInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface ApprovalActionsProps {
  requestId: string;
  status: string;
  requestedBy: string;
  currentUserId: string;
  subjectLabel: string;
}

export function ApprovalActions({
  requestId,
  status,
  requestedBy,
  currentUserId,
  subjectLabel,
}: ApprovalActionsProps) {
  const router = useRouter();
  const { resources } = useAuth();

  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);

  const invalidates = [queryKeys.approvals.tenant(), queryKeys.approvals.detail(requestId)];

  const approveForm = useForm<ApproveActionInput>({
    resolver: zodResolver(approveActionSchema),
    defaultValues: { comment: "" },
  });
  const rejectForm = useForm<RejectActionInput>({
    resolver: zodResolver(rejectActionSchema),
    defaultValues: { reason: "" },
  });

  const approveMutation = useTypedMutation<unknown, ApproveActionInput>(
    async (vars) => {
      const res = await (resources.makerChecker.approveTenant(
        requestId,
        vars as Record<string, unknown>,
      ) as Promise<{ data?: unknown; error?: unknown }>);
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("Request approved", { description: "The operation has been executed." });
        setApproveOpen(false);
        approveForm.reset();
        router.refresh();
      },
      onError: (error) =>
        toast.error("The request was not approved", {
          description: apiErrorMessage(error, "Please try again."),
        }),
    },
  );

  const rejectMutation = useTypedMutation<unknown, RejectActionInput>(
    async (vars) => {
      const res = await (resources.makerChecker.rejectTenant(
        requestId,
        vars as Record<string, unknown>,
      ) as Promise<{ data?: unknown; error?: unknown }>);
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("Request rejected");
        setRejectOpen(false);
        rejectForm.reset();
        router.refresh();
      },
      onError: (error) =>
        toast.error("The request was not rejected", {
          description: apiErrorMessage(error, "Please try again."),
        }),
    },
  );

  const cancelMutation = useTypedMutation<unknown, void>(
    async () => {
      const res = await (resources.makerChecker.cancelTenant(requestId, {}) as Promise<{
        data?: unknown;
        error?: unknown;
      }>);
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("Request cancelled");
        setCancelOpen(false);
        router.refresh();
      },
      onError: (error) =>
        toast.error("The request was not cancelled", {
          description: apiErrorMessage(error, "Please try again."),
        }),
    },
  );

  if (status !== "pending") return null;

  const isOwnRequest = currentUserId === requestedBy;

  return (
    <div className="flex items-center gap-2">
      {isOwnRequest ? (
        <>
          <span className="text-[13px] text-[var(--text-tertiary)]">
            You submitted this request and cannot approve your own request.
          </span>
          <Button variant="destructive" onClick={() => setCancelOpen(true)}>
            Cancel request
          </Button>
        </>
      ) : (
        <>
          <Button
            variant="primary"
            onClick={() => {
              approveForm.reset();
              setApproveOpen(true);
            }}
          >
            Approve
          </Button>
          <Button
            variant="destructive"
            onClick={() => {
              rejectForm.reset();
              setRejectOpen(true);
            }}
          >
            Reject
          </Button>
        </>
      )}

      {/* Approve — checker side: approving EXECUTES the operation once quorum is met. */}
      <Dialog
        open={approveOpen}
        onOpenChange={(o) => {
          if (!o) setApproveOpen(false);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Approve {subjectLabel}</DialogTitle>
            <DialogDescription>
              Approving runs this operation now. When the quorum is met this executes immediately
              and cannot be undone here.
            </DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={approveForm.handleSubmit((values) => approveMutation.mutate(values))}
          >
            <FormField
              control={approveForm.control}
              name="comment"
              label="Comment (optional)"
              render={({ field, id, describedBy, invalid }) => (
                <Textarea
                  id={id}
                  rows={2}
                  aria-describedby={describedBy}
                  aria-invalid={invalid}
                  {...field}
                />
              )}
            />
            <div className="flex gap-3">
              <Button type="submit" disabled={approveMutation.isPending}>
                Approve and execute
              </Button>
              <Button type="button" variant="ghost" onClick={() => setApproveOpen(false)}>
                Cancel
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Reject — required reason. */}
      <Dialog
        open={rejectOpen}
        onOpenChange={(o) => {
          if (!o) setRejectOpen(false);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject {subjectLabel}</DialogTitle>
            <DialogDescription>
              Rejecting closes this request without running the operation.
            </DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={rejectForm.handleSubmit((values) => rejectMutation.mutate(values))}
          >
            <FormField
              control={rejectForm.control}
              name="reason"
              label="Reason"
              required
              helpText="Recorded on the request and the audit log. Minimum 10 characters."
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
              <Button type="submit" variant="destructive" disabled={rejectMutation.isPending}>
                Reject
              </Button>
              <Button type="button" variant="ghost" onClick={() => setRejectOpen(false)}>
                Cancel
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Cancel — requester withdraws (no fields → base ConfirmDialog). */}
      <ConfirmDialog
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        title={`Cancel ${subjectLabel}?`}
        description="This withdraws your pending request. You can re-submit from the originating screen."
        confirmLabel="Cancel request"
        destructive
        busy={cancelMutation.isPending}
        onConfirm={() => cancelMutation.mutate()}
      />
    </div>
  );
}
