"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Button,
  ConfirmDialog,
  FormDialog,
  FormField,
  Textarea,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

const rejectSchema = z.object({
  reason: z.string().trim().min(3, "Give the member a reason they can act on"),
});
type RejectInput = z.infer<typeof rejectSchema>;

export function KycReviewActions({
  submissionId,
  status,
}: {
  submissionId: string;
  status: string;
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);

  const invalidates = [
    queryKeys.members.kycSubmissions(),
    queryKeys.members.kycSubmission(submissionId),
    queryKeys.members.root(),
  ];

  const rejectForm = useForm<RejectInput>({
    resolver: zodResolver(rejectSchema),
    defaultValues: { reason: "" },
  });

  const approveMutation = useTypedMutation<unknown, void>(
    async () => {
      const res = await (resources.members.approveKycSubmission(
        submissionId,
      ) as Promise<{ data?: unknown; error?: unknown }>);
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("KYC approved", {
          description: "The proposed details were applied to the member record.",
        });
        setApproveOpen(false);
        router.refresh();
      },
      onError: (error) =>
        toast.error("The submission was not approved", {
          description: apiErrorMessage(error, "Please try again."),
        }),
    },
  );

  const rejectMutation = useTypedMutation<unknown, RejectInput>(
    async (vars) => {
      const res = await (resources.members.rejectKycSubmission(submissionId, {
        reason: vars.reason,
      }) as Promise<{ data?: unknown; error?: unknown }>);
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("KYC rejected", {
          description: "The member can see the reason and resubmit.",
        });
        setRejectOpen(false);
        rejectForm.reset();
        router.refresh();
      },
      onError: (error) =>
        toast.error("The submission was not rejected", {
          description: apiErrorMessage(error, "Please try again."),
        }),
    },
  );

  if (status !== "pending") return null;

  return (
    <div className="flex gap-3">
      <Button onClick={() => setApproveOpen(true)}>Approve</Button>
      <Button variant="destructive" onClick={() => setRejectOpen(true)}>
        Reject
      </Button>

      {/* Single-reviewer approval — not maker-checker, so the base ConfirmDialog
          is used (not MakerCheckerConfirmDialog) and copy avoids "Request X". */}
      <ConfirmDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        title="Approve KYC submission?"
        description="The proposed details will be written to the member record. Member status is not changed — activation stays a separate approval flow."
        confirmLabel="Approve submission"
        busy={approveMutation.isPending}
        onConfirm={() => approveMutation.mutate()}
      />

      {rejectOpen ? (
        <FormDialog
          title="Reject KYC submission"
          description="The reason is shown to the member so they can fix and resubmit."
          onDismiss={() => setRejectOpen(false)}
          onSubmit={rejectForm.handleSubmit((vars) => rejectMutation.mutate(vars))}
          footer={
            <>
              <Button
                type="button"
                variant="secondary"
                onClick={() => setRejectOpen(false)}
                disabled={rejectMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                variant="destructive"
                disabled={rejectMutation.isPending}
              >
                Reject submission
              </Button>
            </>
          }
        >
          <FormField
            control={rejectForm.control}
            name="reason"
            label="Reason"
            required
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
        </FormDialog>
      ) : null}
    </div>
  );
}
