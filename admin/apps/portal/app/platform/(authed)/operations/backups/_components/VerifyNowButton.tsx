"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, ConfirmDialog, toast } from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import type { BackupVerificationOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

/**
 * Requests an on-demand restore-verify drill via the maker-checker-free ops
 * endpoint. It is not an approval action (the drill touches no live data), so
 * it uses the base ConfirmDialog rather than the maker-checker dialog. A 409
 * (a drill already in flight) is surfaced as a distinct, non-error message.
 */
export function VerifyNowButton() {
  const router = useRouter();
  const { resources } = useAuth();
  const [open, setOpen] = useState(false);

  const mutation = useTypedMutation<BackupVerificationOut | undefined, void>(
    async () => {
      const res = await (resources.ops.triggerVerification() as Promise<{
        data?: BackupVerificationOut;
        error?: unknown;
        response?: Response;
      }>);
      if (res.error) {
        throw Object.assign(new Error("verification request failed"), {
          status: res.response?.status,
        });
      }
      return res.data;
    },
    {
      invalidates: [queryKeys.ops.backups()],
      onSuccess: () => {
        toast.success("Restore-verify drill requested", {
          description: "The drill runs in the background; refresh for its result.",
        });
        setOpen(false);
        router.refresh();
      },
      onError: (error) => {
        setOpen(false);
        if ((error as { status?: number }).status === 409) {
          toast.error("A verification is already running.");
          return;
        }
        toast.error("The drill was not started", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <>
      <Button onClick={() => setOpen(true)}>Verify now</Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Run a restore-verify drill now?"
        description="This restores the latest backup into a throwaway database, smoke-tests it, and records the result. It does not touch live data."
        confirmLabel="Run drill"
        busy={mutation.isPending}
        onConfirm={() => mutation.mutate()}
      />
    </>
  );
}
