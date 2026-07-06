"use client";

import { useState } from "react";
import { Button, Card, Checkbox, Label, toast } from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import type { SaccoKycRequirementsOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function SaccoKycRequirementsForm({
  initial,
}: {
  initial: SaccoKycRequirementsOut;
}) {
  const { resources } = useAuth();
  const [items, setItems] = useState(initial.items);

  const mutation = useTypedMutation<SaccoKycRequirementsOut, Record<string, boolean>>(
    async (required) => {
      // putSaccoRequirements is typed Promise<never> (as-never paths); cast
      // to the real { data, error } shape.
      const res = await (resources.kyc.putSaccoRequirements({
        required,
      }) as Promise<{ data?: SaccoKycRequirementsOut; error?: unknown }>);
      if (res.error || !res.data) throw res.error ?? new Error("Empty response");
      return res.data;
    },
    {
      invalidates: [queryKeys.kyc.root()],
      onSuccess: (data) => {
        setItems(data.items);
        toast.success("SACCO KYC requirements saved");
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
    // Locked keys are ignored server-side; keep the payload to real toggles.
    mutation.mutate(
      Object.fromEntries(
        items.filter((item) => !item.locked).map((item) => [item.key, item.required]),
      ),
    );
  };

  return (
    <Card className="flex max-w-xl flex-col gap-4 p-6">
      <p className="text-[13px] text-[var(--text-secondary)]">
        Fields required for a SACCO&apos;s organization KYC to count as complete.
        Applies to all tenants. Locked minimums cannot be toggled off.
      </p>
      <ul className="flex flex-col">
        {items.map((item) => (
          <li key={item.key} className="flex items-center gap-3 py-2">
            <Checkbox
              id={`req-${item.key}`}
              checked={item.required}
              disabled={item.locked}
              onCheckedChange={(checked) => toggle(item.key, checked === true)}
            />
            <Label htmlFor={`req-${item.key}`}>{item.label}</Label>
            {item.locked ? (
              <span className="text-[11px] text-[var(--text-tertiary)]">
                Always required
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      <div>
        <Button onClick={save} disabled={mutation.isPending}>
          Save requirements
        </Button>
      </div>
    </Card>
  );
}
