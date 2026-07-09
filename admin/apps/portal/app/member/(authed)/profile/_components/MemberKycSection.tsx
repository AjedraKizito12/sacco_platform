"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Card, StatusBadge, toast } from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  toMemberKycPayload,
  type KycSubmissionOut,
  type MemberKycFormInput,
  type MemberSelfKycOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";
import { KycCompletionCard } from "@/components/kyc/KycCompletionCard";
import { MemberKycFormDialog } from "./MemberKycFormDialog";

export function MemberKycSection({ initial }: { initial: MemberSelfKycOut }) {
  const router = useRouter();
  const { resources } = useAuth();
  const [formOpen, setFormOpen] = useState(false);

  const submission = initial.latest_submission;
  const isPending = submission?.status === "pending";

  const mutation = useTypedMutation<KycSubmissionOut, MemberKycFormInput>(
    async (input) => {
      const res = await (resources.member.submitKyc(
        toMemberKycPayload(input) as unknown as Record<string, unknown>,
      ) as Promise<{ data?: KycSubmissionOut; error?: unknown }>);
      if (res.error || !res.data) throw res.error ?? new Error("Empty response");
      return res.data;
    },
    {
      invalidates: [queryKeys.member.kyc()],
      onSuccess: () => {
        toast.success("KYC submitted", {
          description: "SACCO staff will review your details.",
        });
        setFormOpen(false);
        router.refresh();
      },
      onError: (error) => {
        toast.error("Your KYC was not submitted", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const dialogTitle =
    submission == null
      ? "Complete your KYC"
      : submission.status === "rejected"
        ? "Resubmit your KYC"
        : "Edit your KYC";

  // Prefill the rejected proposal so the member fixes it rather than
  // retyping; otherwise start from the current approved/on-record values.
  const formValues =
    submission?.status === "rejected" ? submission.proposed : initial.values;

  return (
    <section className="space-y-4">
      <h2 className="text-[length:var(--text-h5)] font-semibold">KYC</h2>

      {submission == null ? (
        <Card className="flex items-center justify-between gap-4 p-4">
          <p>Complete your KYC so the SACCO can verify your details.</p>
          <Button onClick={() => setFormOpen(true)}>Complete KYC</Button>
        </Card>
      ) : isPending ? (
        <Card className="flex items-center justify-between gap-4 p-4">
          <p>Your KYC is under review.</p>
          <StatusBadge entity="kyc_submission" status="pending" />
        </Card>
      ) : submission.status === "rejected" ? (
        <Card className="space-y-3 p-4">
          <div className="flex items-center justify-between gap-4">
            <p>Your KYC submission was rejected.</p>
            <StatusBadge entity="kyc_submission" status="rejected" />
          </div>
          <p className="text-[var(--text-secondary)]">{submission.rejection_reason}</p>
          <Button onClick={() => setFormOpen(true)}>Resubmit KYC</Button>
        </Card>
      ) : (
        <Card className="flex items-center justify-between gap-4 p-4">
          <p>Your KYC details were approved.</p>
          <div className="flex items-center gap-3">
            <StatusBadge entity="kyc_submission" status="approved" />
            <Button variant="secondary" onClick={() => setFormOpen(true)}>
              Edit KYC
            </Button>
          </div>
        </Card>
      )}

      <KycCompletionCard completion={initial.completion} />

      {formOpen && !isPending ? (
        <MemberKycFormDialog
          title={dialogTitle}
          initialValues={formValues}
          busy={mutation.isPending}
          onDismiss={() => setFormOpen(false)}
          onSubmit={(input) => mutation.mutate(input)}
        />
      ) : null}
    </section>
  );
}
