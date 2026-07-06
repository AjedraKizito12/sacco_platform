"use client";

import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  FormattedDateTime,
  ReadOnlyField,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import type { OrganizationKycOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";
import { KycCompletionCard } from "@/components/kyc/KycCompletionCard";

/**
 * Read-only SACCO org-KYC oversight card on the platform tenant detail.
 * Verify is a direct admin operation (no maker-checker) and the API returns
 * 409 when the profile is incomplete — the disabled state mirrors that.
 */
export function TenantKycSection({
  tenantId,
  initial,
  canVerify,
}: {
  tenantId: string;
  initial: OrganizationKycOut;
  canVerify: boolean;
}) {
  const { resources } = useAuth();
  const [latest, setLatest] = useState(initial);
  const [confirming, setConfirming] = useState<"verify" | "unverify" | null>(null);

  const mutation = useTypedMutation<OrganizationKycOut, "verify" | "unverify">(
    async (action) => {
      // verifyTenant/unverifyTenant are typed Promise<never> (as-never
      // paths); cast to the real { data, error } shape.
      const call =
        action === "verify"
          ? resources.kyc.verifyTenant(tenantId)
          : resources.kyc.unverifyTenant(tenantId);
      const res = await (call as Promise<{ data?: OrganizationKycOut; error?: unknown }>);
      if (res.error || !res.data) throw res.error ?? new Error("Empty response");
      return res.data;
    },
    {
      invalidates: [queryKeys.tenants.kyc(tenantId)],
      onSuccess: (data, action) => {
        setLatest(data);
        setConfirming(null);
        toast.success(
          action === "verify" ? "Organization KYC verified" : "Verification removed",
        );
      },
      onError: (error) => {
        setConfirming(null);
        toast.error("The verification change failed", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const missingCount = latest.completion.missing_required.length;
  const values = latest.values as Record<string, string | null>;

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4 p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="text-[var(--text-h5)] font-semibold">Organization KYC</h2>
            {latest.verified ? (
              <Badge variant="success">Verified by platform</Badge>
            ) : (
              <Badge variant="neutral">Not verified</Badge>
            )}
          </div>
          {canVerify ? (
            latest.verified ? (
              <Button variant="ghost" onClick={() => setConfirming("unverify")}>
                Remove verification
              </Button>
            ) : (
              <Button
                onClick={() => setConfirming("verify")}
                disabled={!latest.completion.is_complete}
              >
                Verify
              </Button>
            )
          ) : null}
        </div>
        {latest.verified && latest.verified_at ? (
          <p className="text-[13px] text-[var(--text-secondary)]">
            Verified <FormattedDateTime value={latest.verified_at} />
          </p>
        ) : null}
        {!latest.verified && !latest.completion.is_complete ? (
          <p className="text-[13px] text-[var(--text-secondary)]">
            {missingCount} required item{missingCount === 1 ? " is" : "s are"} still
            missing — verification unlocks when the SACCO completes them.
          </p>
        ) : null}
        <div className="grid grid-cols-2 gap-5">
          {latest.completion.items.map((item) => (
            <ReadOnlyField
              key={item.key}
              label={item.label}
              value={values[item.key] ?? "—"}
            />
          ))}
        </div>
      </Card>

      <KycCompletionCard completion={latest.completion} />

      <ConfirmDialog
        open={confirming === "verify"}
        onOpenChange={(next) => setConfirming(next ? "verify" : null)}
        title="Verify organization KYC?"
        description="This marks the SACCO's self-attested KYC as verified by the platform. Any later change to their KYC values resets it."
        confirmLabel="Verify organization KYC"
        busy={mutation.isPending}
        onConfirm={() => mutation.mutate("verify")}
      />
      <ConfirmDialog
        open={confirming === "unverify"}
        onOpenChange={(next) => setConfirming(next ? "unverify" : null)}
        title="Remove verification?"
        description="The SACCO's organization KYC will show as not verified until verified again."
        confirmLabel="Remove verification"
        destructive
        busy={mutation.isPending}
        onConfirm={() => mutation.mutate("unverify")}
      />
    </div>
  );
}
