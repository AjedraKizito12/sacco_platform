// admin/apps/portal/app/(tenant-authed)/members/[id]/_components/ChangeMemberStatusButton.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  FormDialog,
  FormField,
  MakerCheckerConfirmDialog,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
  toast,
} from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import {
  memberStatusChangeSchema,
  type MemberStatusChangeInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

// Locked drift: the backend status-change only accepts these three. The shared
// Zod `memberStatusSchema` enum is broader; constrain the UI so it can't 422.
const STATUS_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "suspended", label: "Suspended" },
  { value: "exited", label: "Exited" },
] as const;

export function ChangeMemberStatusButton({
  memberId,
  currentStatus,
}: {
  memberId: string;
  currentStatus: string;
}) {
  const router = useRouter();
  const { resources } = useAuth();

  const [formOpen, setFormOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, setPending] = useState<MemberStatusChangeInput | null>(null);

  // Fresh idempotency key per form instance; persists across confirm retries.
  const [idemKey] = useState(() => crypto.randomUUID());
  const form = useForm<MemberStatusChangeInput>({
    resolver: zodResolver(memberStatusChangeSchema),
    defaultValues: { new_status: "active", reason: "", idempotency_key: idemKey },
  });

  const mutation = useTypedMutation<unknown, MemberStatusChangeInput>(
    async (vars) => {
      const res = await (
        resources.members.changeStatus(memberId, vars as Record<string, unknown>) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      onSuccess: () => {
        toast.success("Status change requested — pending approval");
        setConfirmOpen(false);
        setFormOpen(false);
        setPending(null);
        form.reset({ new_status: "active", reason: "", idempotency_key: idemKey });
        router.refresh();
      },
      onError: (error) => {
        toast.error("The status change was not requested", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <>
      <Button variant="secondary" onClick={() => { form.reset({ new_status: "active", reason: "", idempotency_key: idemKey }); setFormOpen(true); }}>
        Change status
      </Button>

      {formOpen ? (
        <FormDialog
          title="Change member status"
          description={`Current status is ${currentStatus}. This creates an approval request; the change applies once another operator approves it.`}
          onDismiss={() => setFormOpen(false)}
          onSubmit={form.handleSubmit((values) => {
            setPending(values);
            setFormOpen(false);
            setConfirmOpen(true);
          })}
          footer={
            <>
              <Button type="button" variant="ghost" onClick={() => setFormOpen(false)}>Cancel</Button>
              <Button type="submit">Request status change</Button>
            </>
          }
        >
          <FormField control={form.control} name="new_status" label="New status" required
            render={({ field, id, describedBy, invalid }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )} />
          <FormField control={form.control} name="reason" label="Reason" required
            helpText="Recorded on the approval request and the audit log. Minimum 10 characters."
            render={({ field, id, describedBy, invalid }) => (
              <Textarea id={id} rows={3} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
            )} />
        </FormDialog>
      ) : null}

      <MakerCheckerConfirmDialog
        open={confirmOpen}
        onOpenChange={(o) => { setConfirmOpen(o); if (!o) setPending(null); }}
        operationLabel="member status change"
        subjectLabel={pending?.new_status ?? ""}
        busy={mutation.isPending}
        onConfirm={() => { if (pending) mutation.mutate(pending); }}
      />
    </>
  );
}
