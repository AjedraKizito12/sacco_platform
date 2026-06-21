// admin/apps/portal/app/(tenant-authed)/shares/accounts/[id]/_components/AccountActions.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  FormField,
  Input,
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
  purchaseSharesSchema,
  redeemSharesSchema,
  type PurchaseSharesInput,
  type RedeemSharesInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface GlAccountOption {
  id: string;
  code: string;
  name: string;
  account_type: string;
}

export function AccountActions({
  accountId,
  glAccounts,
}: {
  accountId: string;
  glAccounts: GlAccountOption[];
}) {
  const router = useRouter();
  const { resources } = useAuth();

  const [purchaseOpen, setPurchaseOpen] = useState(false);
  const [redeemOpen, setRedeemOpen] = useState(false);
  const [redeemConfirm, setRedeemConfirm] = useState(false);
  const [pendingRedeem, setPendingRedeem] = useState<RedeemSharesInput | null>(null);

  // Fresh idempotency keys per form instance; persist across confirm retries.
  const [purchaseKey] = useState(() => crypto.randomUUID());
  const [redeemKey] = useState(() => crypto.randomUUID());

  const purchaseForm = useForm<PurchaseSharesInput>({
    resolver: zodResolver(purchaseSharesSchema),
    defaultValues: { quantity: "", payment_account_id: "", idempotency_key: purchaseKey },
  });
  const redeemForm = useForm<RedeemSharesInput>({
    resolver: zodResolver(redeemSharesSchema),
    defaultValues: { quantity: "", payment_account_id: "", reason: "", idempotency_key: redeemKey },
  });

  const purchaseMutation = useTypedMutation<unknown, PurchaseSharesInput>(
    async (vars) => {
      const res = await (
        resources.shares.purchase(accountId, vars as Record<string, unknown>) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      onSuccess: () => {
        toast.success("Shares purchased");
        setPurchaseOpen(false);
        purchaseForm.reset({ quantity: "", payment_account_id: "", idempotency_key: purchaseKey });
        router.refresh();
      },
      onError: (error) => {
        toast.error("The purchase was not posted", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const redeemMutation = useTypedMutation<unknown, RedeemSharesInput>(
    async (vars) => {
      const res = await (
        resources.shares.redeem(accountId, vars as Record<string, unknown>) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      onSuccess: () => {
        toast.success("Redemption requested — pending approval");
        setRedeemConfirm(false);
        setRedeemOpen(false);
        setPendingRedeem(null);
        redeemForm.reset({ quantity: "", payment_account_id: "", reason: "", idempotency_key: redeemKey });
        router.refresh();
      },
      onError: (error) => {
        toast.error("The redemption was not requested", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const glSelect = (
    field: { value: string; onChange: (v: string) => void },
    id: string,
    describedBy: string | undefined,
    invalid: boolean,
  ) => (
    <Select value={field.value} onValueChange={field.onChange}>
      <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
        <SelectValue placeholder="Choose a GL account…" />
      </SelectTrigger>
      <SelectContent>
        {glAccounts.map((a) => (
          <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  return (
    <div className="flex items-center gap-2">
      <Button onClick={() => { purchaseForm.reset({ quantity: "", payment_account_id: "", idempotency_key: purchaseKey }); setPurchaseOpen(true); }}>
        Purchase
      </Button>
      <Button variant="secondary" onClick={() => { redeemForm.reset({ quantity: "", payment_account_id: "", reason: "", idempotency_key: redeemKey }); setRedeemOpen(true); }}>
        Redeem
      </Button>

      {/* Purchase — direct (no maker-checker) */}
      <Dialog open={purchaseOpen} onOpenChange={(o) => { if (!o) setPurchaseOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Purchase shares</DialogTitle>
            <DialogDescription>Buy shares into this account.</DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={purchaseForm.handleSubmit((values) => purchaseMutation.mutate(values))}
          >
            <FormField control={purchaseForm.control} name="quantity" label="Quantity" required
              render={({ field, id, describedBy, invalid }) => (
                <Input id={id} inputMode="numeric" aria-describedby={describedBy}
                  aria-invalid={invalid} {...field} />
              )} />
            <FormField control={purchaseForm.control} name="payment_account_id" label="Cash / payment GL account" required
              render={({ field, id, describedBy, invalid }) => glSelect(field, id, describedBy, invalid)} />
            <div className="flex gap-3">
              <Button type="submit" disabled={purchaseMutation.isPending}>Post purchase</Button>
              <Button type="button" variant="ghost" onClick={() => setPurchaseOpen(false)}>Cancel</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Redeem — maker-checker */}
      <Dialog open={redeemOpen} onOpenChange={(o) => { if (!o) setRedeemOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Redeem shares</DialogTitle>
            <DialogDescription>
              This creates an approval request; the redemption posts once another operator approves it.
            </DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={redeemForm.handleSubmit((values) => {
              setPendingRedeem(values);
              setRedeemOpen(false);
              setRedeemConfirm(true);
            })}
          >
            <FormField control={redeemForm.control} name="quantity" label="Quantity" required
              render={({ field, id, describedBy, invalid }) => (
                <Input id={id} inputMode="numeric" aria-describedby={describedBy}
                  aria-invalid={invalid} {...field} />
              )} />
            <FormField control={redeemForm.control} name="payment_account_id" label="Cash / payment GL account" required
              render={({ field, id, describedBy, invalid }) => glSelect(field, id, describedBy, invalid)} />
            <FormField control={redeemForm.control} name="reason" label="Reason"
              render={({ field, id, describedBy, invalid }) => (
                <Textarea id={id} rows={2} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <div className="flex gap-3">
              <Button type="submit">Request redemption</Button>
              <Button type="button" variant="ghost" onClick={() => setRedeemOpen(false)}>Cancel</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <MakerCheckerConfirmDialog
        open={redeemConfirm}
        onOpenChange={(o) => { setRedeemConfirm(o); if (!o) setPendingRedeem(null); }}
        operationLabel="share redemption"
        subjectLabel={pendingRedeem ? `${pendingRedeem.quantity} shares` : ""}
        busy={redeemMutation.isPending}
        onConfirm={() => { if (pendingRedeem) redeemMutation.mutate(pendingRedeem); }}
      />
    </div>
  );
}
