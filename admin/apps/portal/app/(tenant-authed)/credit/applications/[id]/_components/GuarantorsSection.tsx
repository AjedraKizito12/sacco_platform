// admin/apps/portal/app/(tenant-authed)/credit/applications/[id]/_components/GuarantorsSection.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Card,
  Checkbox,
  ConfirmDialog,
  FormDialog,
  FormField,
  Money,
  StatusBadge,
  toast,
} from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import {
  guarantorNominateSchema,
  type GuarantorNominateInput,
  type GuarantorOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface MemberOption {
  id: string;
  full_name: string;
  member_number: string;
}

export function GuarantorsSection({
  applicationId,
  guarantors,
  members,
}: {
  applicationId: string;
  guarantors: GuarantorOut[];
  members: MemberOption[];
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const memberById = new Map(members.map((m) => [m.id, m]));
  const label = (id: string) => {
    const m = memberById.get(id);
    return m ? `${m.full_name} (${m.member_number})` : id;
  };

  const [nominateOpen, setNominateOpen] = useState(false);
  const [consent, setConsent] = useState<
    { guarantorId: string; memberId: string; action: "accept" | "decline" } | null
  >(null);

  const nominatable = members.filter(
    (m) => !guarantors.some((g) => g.guarantor_member_id === m.id),
  );

  const nominateForm = useForm<GuarantorNominateInput>({
    resolver: zodResolver(guarantorNominateSchema),
    defaultValues: { guarantor_member_ids: [] },
  });

  const addMutation = useTypedMutation<unknown, GuarantorNominateInput>(
    async (vars) => {
      const res = await (
        resources.credit.addGuarantor(applicationId, vars) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      onSuccess: () => {
        toast.success("Guarantors added");
        setNominateOpen(false);
        nominateForm.reset({ guarantor_member_ids: [] });
        router.refresh();
      },
      onError: (error) => {
        toast.error("The guarantors were not added", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const consentMutation = useTypedMutation<
    unknown,
    { guarantorId: string; memberId: string; action: "accept" | "decline" }
  >(
    async (vars) => {
      const call =
        vars.action === "accept"
          ? resources.credit.acceptGuarantor
          : resources.credit.declineGuarantor;
      const res = await (call(vars.guarantorId, {
        guarantor_member_id: vars.memberId,
      }) as Promise<{ data?: unknown; error?: unknown }>);
      if (res.error) throw res.error;
      return res.data;
    },
    {
      onSuccess: (_data, vars) => {
        toast.success(vars.action === "accept" ? "Guarantor accepted" : "Guarantor declined");
        setConsent(null);
        router.refresh();
      },
      onError: (error) => {
        toast.error("The action failed", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <Card className="flex flex-col gap-3 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-[var(--text-h5)] font-semibold">Guarantors</h2>
        <Button variant="secondary" onClick={() => setNominateOpen(true)} disabled={nominatable.length === 0}>
          Add guarantor
        </Button>
      </div>

      {guarantors.length === 0 ? (
        <p className="text-[var(--text-secondary)]">No guarantors nominated.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-[var(--border-subtle)]">
          {guarantors.map((g) => (
            <li key={g.id} className="flex items-center justify-between gap-4 py-3">
              <div className="flex flex-col">
                <span className="font-medium">{label(g.guarantor_member_id)}</span>
                <span className="text-[var(--text-secondary)]">
                  <Money amount={g.guaranteed_amount} /> guaranteed
                </span>
              </div>
              <div className="flex items-center gap-3">
                <StatusBadge entity="guarantor" status={g.status} />
                {g.status === "pending" ? (
                  <>
                    <Button
                      onClick={() =>
                        setConsent({ guarantorId: g.id, memberId: g.guarantor_member_id, action: "accept" })
                      }
                    >
                      Accept
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() =>
                        setConsent({ guarantorId: g.id, memberId: g.guarantor_member_id, action: "decline" })
                      }
                    >
                      Decline
                    </Button>
                  </>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={consent !== null}
        onOpenChange={(o) => { if (!o) setConsent(null); }}
        title={consent?.action === "decline" ? "Decline guarantor" : "Accept guarantor"}
        description={
          consent?.action === "decline"
            ? "Record that this member has declined to guarantee the loan."
            : "Record that this member has consented to guarantee the loan."
        }
        confirmLabel={consent?.action === "decline" ? "Decline" : "Accept"}
        destructive={consent?.action === "decline"}
        busy={consentMutation.isPending}
        onConfirm={() => { if (consent) consentMutation.mutate(consent); }}
      />

      {nominateOpen ? (
        <FormDialog
          title="Add guarantors"
          description="Select members to nominate as guarantors for this application."
          onDismiss={() => setNominateOpen(false)}
          onSubmit={nominateForm.handleSubmit((values) => addMutation.mutate(values))}
          footer={
            <>
              <Button type="button" variant="ghost" onClick={() => setNominateOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={addMutation.isPending}>
                {addMutation.isPending ? "Adding…" : "Add selected"}
              </Button>
            </>
          }
        >
          <FormField control={nominateForm.control} name="guarantor_member_ids" label="Members" required
            render={({ field }) => (
              <div className="-mx-2 flex max-h-80 flex-col gap-0.5 overflow-y-auto">
                {nominatable.map((m) => {
                  const current = (field.value ?? []) as string[];
                  const checked = current.includes(m.id);
                  return (
                    <label
                      key={m.id}
                      htmlFor={`nominate-${m.id}`}
                      className="flex cursor-pointer items-center gap-3 rounded-[var(--radius-md)] px-2 py-2 hover:bg-[var(--surface-hover)]"
                    >
                      <Checkbox
                        id={`nominate-${m.id}`}
                        checked={checked}
                        onCheckedChange={(c) => {
                          const next = new Set<string>(current);
                          if (c) next.add(m.id);
                          else next.delete(m.id);
                          field.onChange([...next]);
                        }}
                      />
                      <span className="flex flex-col">
                        <span className="text-sm text-[var(--text-primary)]">{m.full_name}</span>
                        <span className="text-xs text-[var(--text-secondary)]">{m.member_number}</span>
                      </span>
                    </label>
                  );
                })}
              </div>
            )} />
        </FormDialog>
      ) : null}
    </Card>
  );
}
