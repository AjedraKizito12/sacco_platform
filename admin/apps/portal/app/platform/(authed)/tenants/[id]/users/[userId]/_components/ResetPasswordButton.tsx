"use client";

import { useState } from "react";
import { Button, toast } from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";
import { OneTimeModal } from "@/components/OneTimeModal";

interface ResetToken {
  token: string;
  ttlSeconds: number;
}

export function ResetPasswordButton({
  tenantId,
  userId,
}: {
  tenantId: string;
  userId: string;
}) {
  const { resources } = useAuth();
  const [reset, setReset] = useState<ResetToken | null>(null);

  const mutation = useTypedMutation<
    { password_reset_token: string; password_reset_expires_in: number },
    void
  >(
    async () => {
      const res = await (
        resources.tenants.resetUserPassword(tenantId, userId) as Promise<{
          data?: { password_reset_token: string; password_reset_expires_in: number };
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data!;
    },
    {
      onSuccess: (data) => {
        setReset({
          token: data.password_reset_token,
          ttlSeconds: data.password_reset_expires_in,
        });
      },
      onError: (error) => {
        toast.error("The reset link was not generated", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <>
      <Button variant="secondary" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
        Reset password
      </Button>
      <OneTimeModal
        open={reset !== null}
        onAcknowledge={() => setReset(null)}
        title="Password reset link"
        description="Share this one-time link with the user out of band. It won't be shown again."
        payload={reset?.token ?? ""}
        payloadLabel="Password reset token"
        warningCopy={`Valid for ${Math.round((reset?.ttlSeconds ?? 0) / 3600)} hours.`}
      />
    </>
  );
}
