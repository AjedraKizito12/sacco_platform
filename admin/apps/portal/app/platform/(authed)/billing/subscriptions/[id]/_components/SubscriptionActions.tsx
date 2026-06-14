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
  MakerCheckerConfirmDialog,
  Textarea,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  subscriptionCancelSchema,
  type SubscriptionCancelInput,
  type SubscriptionOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

type CancelMode = "at_period_end" | "immediate";

export function SubscriptionActions({
  subscription,
  canWrite,
}: {
  subscription: SubscriptionOut;
  canWrite: boolean;
}) {
  const router = useRouter();
  const { resources } = useAuth();

  // Reason-collection dialog (shared by both cancel modes).
  const [reasonMode, setReasonMode] = useState<CancelMode | null>(null);
  // Maker-checker confirm for the immediate path.
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingReason, setPendingReason] = useState<string | null>(null);
  const [reactivateOpen, setReactivateOpen] = useState(false);

  const form = useForm<SubscriptionCancelInput>({
    resolver: zodResolver(subscriptionCancelSchema),
    defaultValues: { reason: "" },
  });

  const invalidates = [
    queryKeys.billing.subscriptions(),
    queryKeys.billing.subscription(subscription.id),
  ];

  const cancelMutation = useTypedMutation<unknown, { reason: string; mode: CancelMode }>(
    async ({ reason, mode }) => {
      // resources.billing.cancelSubscription is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.billing.cancelSubscription(subscription.id, { reason }, { mode }) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: (_data, vars) => {
        if (vars.mode === "immediate") {
          toast.success("Approval request created", {
            description: "The subscription will be cancelled once another platform user approves it.",
          });
        } else {
          toast.success("Cancellation scheduled", {
            description: "The subscription will end at the close of the current period.",
          });
        }
        setReasonMode(null);
        setConfirmOpen(false);
        setPendingReason(null);
        form.reset();
        router.refresh();
      },
      onError: (error) => {
        toast.error("The cancellation was not processed", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const reactivation = useTypedMutation<unknown, void>(
    async () => {
      const res = await (
        resources.billing.reactivateSubscription(subscription.id) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates,
      onSuccess: () => {
        toast.success("Subscription reactivated");
        setReactivateOpen(false);
        router.refresh();
      },
      onError: (error) => {
        toast.error("The subscription was not reactivated", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  if (!canWrite) return null;

  const status = subscription.status;
  const cancellable = status === "active" || status === "trialing" || status === "past_due";
  const reactivatable = status === "suspended";

  return (
    <div className="flex items-center gap-2">
      {cancellable ? (
        <>
          <Button variant="secondary" onClick={() => { form.reset(); setReasonMode("at_period_end"); }}>
            Cancel at period end
          </Button>
          <Button variant="destructive" onClick={() => { form.reset(); setReasonMode("immediate"); }}>
            Cancel immediately
          </Button>
        </>
      ) : null}
      {reactivatable ? (
        <Button variant="primary" onClick={() => setReactivateOpen(true)}>Reactivate</Button>
      ) : null}

      {/* Reason collection — both modes funnel through here first. */}
      <Dialog open={reasonMode !== null} onOpenChange={(o) => { if (!o) setReasonMode(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {reasonMode === "immediate" ? "Cancel immediately" : "Cancel at period end"}
            </DialogTitle>
            <DialogDescription>
              {reasonMode === "immediate"
                ? "Provide a reason. This creates an approval request; another authorised user must approve before cancellation runs."
                : "Provide a reason. The subscription will end at the close of the current billing period."}
            </DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={form.handleSubmit(({ reason }) => {
              if (reasonMode === "immediate") {
                setPendingReason(reason);
                setReasonMode(null);
                setConfirmOpen(true);
              } else {
                cancelMutation.mutate({ reason, mode: "at_period_end" });
              }
            })}
          >
            <FormField control={form.control} name="reason" label="Reason" required
              helpText="Recorded on the subscription and the audit log. Minimum 10 characters."
              render={({ field, id, describedBy, invalid }) => (
                <Textarea id={id} rows={3} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <div className="flex gap-3">
              <Button type="submit" variant={reasonMode === "immediate" ? "destructive" : "primary"} disabled={cancelMutation.isPending}>
                {reasonMode === "immediate" ? "Request immediate cancellation" : "Schedule cancellation"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setReasonMode(null)}>Back</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Immediate cancel = maker-checker. */}
      <MakerCheckerConfirmDialog
        open={confirmOpen}
        onOpenChange={(o) => {
          setConfirmOpen(o);
          if (!o) setPendingReason(null);
        }}
        operationLabel="immediate subscription cancellation"
        busy={cancelMutation.isPending}
        onConfirm={() => {
          if (pendingReason) cancelMutation.mutate({ reason: pendingReason, mode: "immediate" });
        }}
      />

      <ConfirmDialog
        open={reactivateOpen}
        onOpenChange={setReactivateOpen}
        title="Reactivate subscription?"
        description="This restores the subscription to active immediately. No approval is required."
        confirmLabel="Reactivate subscription"
        busy={reactivation.isPending}
        onConfirm={() => reactivation.mutate()}
      />
    </div>
  );
}
