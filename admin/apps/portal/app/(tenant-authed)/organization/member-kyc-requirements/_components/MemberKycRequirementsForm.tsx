"use client";

import { useState } from "react";
import { toast } from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import type { MemberKycRequirementsOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";
import { KycRequirementsToggles } from "@/components/kyc/KycRequirementsToggles";

export function MemberKycRequirementsForm({
  initial,
}: {
  initial: MemberKycRequirementsOut;
}) {
  const { resources } = useAuth();
  const [items, setItems] = useState(initial.items);

  const mutation = useTypedMutation<MemberKycRequirementsOut, Record<string, boolean>>(
    async (required) => {
      // putKycRequirements is typed Promise<never> (as-never paths); cast
      // to the real { data, error } shape.
      const res = await (resources.members.putKycRequirements({
        required,
      }) as Promise<{ data?: MemberKycRequirementsOut; error?: unknown }>);
      if (res.error || !res.data) throw res.error ?? new Error("Empty response");
      return res.data;
    },
    {
      invalidates: [queryKeys.members.root(), queryKeys.members.kycRequirements()],
      onSuccess: (data) => {
        setItems(data.items);
        toast.success("Member KYC requirements saved");
      },
      onError: (error) => {
        toast.error("The requirements were not saved", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const toggle = (key: string, next: boolean) => {
    setItems((prev) =>
      prev.map((item) => (item.key === key ? { ...item, required: next } : item)),
    );
  };

  const save = () => {
    mutation.mutate(
      Object.fromEntries(
        items.filter((item) => !item.locked).map((item) => [item.key, item.required]),
      ),
    );
  };

  return (
    <KycRequirementsToggles
      items={items}
      description="Fields a member must provide for their KYC to count as complete in this SACCO. Locked minimums cannot be toggled off. Completion is informational — it does not block activation or transactions."
      busy={mutation.isPending}
      onToggle={toggle}
      onSave={save}
    />
  );
}
