// admin/apps/portal/app/(tenant-authed)/savings/accounts/[id]/_components/AccountActions.tsx
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
  MakerCheckerConfirmDialog,
  MoneyInput,
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
  depositSchema,
  withdrawSchema,
  type DepositInput,
  type WithdrawInput,
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

  const [depositOpen, setDepositOpen] = useState(false);
  const [withdrawOpen, setWithdrawOpen] = useState(false);
  const [withdrawConfirm, setWithdrawConfirm] = useState(false);
  const [pendingWithdraw, setPendingWithdraw] = useState<WithdrawInput | null>(null);

  // Fresh idempotency keys per form instance; persist across confirm retries.
  const [depositKey] = useState(() => crypto.randomUUID());
  const [withdrawKey] = useState(() => crypto.randomUUID());

  const depositForm = useForm<DepositInput>({
    resolver: zodResolver(depositSchema),
    defaultValues: { amount: "", payment_account_id: "", idempotency_key: depositKey, narration: "" },
  });
  const withdrawForm = useForm<WithdrawInput>({
    resolver: zodResolver(withdrawSchema),
    defaultValues: { amount: "", payment_account_id: "", idempotency_key: withdrawKey, narration: "" },
  });

  const depositMutation = useTypedMutation<unknown, DepositInput>(
    async (vars) => {
      const res = await (
        resources.savings.deposit(accountId, vars as Record<string, unknown>) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      onSuccess: () => {
        toast.success("Deposit posted");
        setDepositOpen(false);
        depositForm.reset({ amount: "", payment_account_id: "", idempotency_key: depositKey, narration: "" });
        router.refresh();
      },
      onError: (error) => {
        toast.error("The deposit was not posted", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const withdrawMutation = useTypedMutation<unknown, WithdrawInput>(
    async (vars) => {
      const res = await (
        resources.savings.withdraw(accountId, vars as Record<string, unknown>) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      onSuccess: () => {
        toast.success("Withdrawal requested — pending approval");
        setWithdrawConfirm(false);
        setWithdrawOpen(false);
        setPendingWithdraw(null);
        withdrawForm.reset({ amount: "", payment_account_id: "", idempotency_key: withdrawKey, narration: "" });
        router.refresh();
      },
      onError: (error) => {
        toast.error("The withdrawal was not requested", {
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
      <Button onClick={() => { depositForm.reset({ amount: "", payment_account_id: "", idempotency_key: depositKey, narration: "" }); setDepositOpen(true); }}>
        Deposit
      </Button>
      <Button variant="secondary" onClick={() => { withdrawForm.reset({ amount: "", payment_account_id: "", idempotency_key: withdrawKey, narration: "" }); setWithdrawOpen(true); }}>
        Withdraw
      </Button>

      {/* Deposit — direct (no maker-checker) */}
      <Dialog open={depositOpen} onOpenChange={(o) => { if (!o) setDepositOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Deposit</DialogTitle>
            <DialogDescription>Post a deposit to this savings account.</DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={depositForm.handleSubmit((values) => depositMutation.mutate(values))}
          >
            <FormField control={depositForm.control} name="amount" label="Amount" required
              render={({ field, id, describedBy, invalid }) => (
                <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
                  value={field.value ?? ""} onValueChange={field.onChange}
                  onBlur={field.onBlur} name={field.name} ref={field.ref} />
              )} />
            <FormField control={depositForm.control} name="payment_account_id" label="Cash / payment GL account" required
              render={({ field, id, describedBy, invalid }) => glSelect(field, id, describedBy, invalid)} />
            <FormField control={depositForm.control} name="narration" label="Narration"
              render={({ field, id, describedBy, invalid }) => (
                <Textarea id={id} rows={2} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <div className="flex gap-3">
              <Button type="submit" disabled={depositMutation.isPending}>Post deposit</Button>
              <Button type="button" variant="ghost" onClick={() => setDepositOpen(false)}>Cancel</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Withdraw — maker-checker */}
      <Dialog open={withdrawOpen} onOpenChange={(o) => { if (!o) setWithdrawOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Withdraw</DialogTitle>
            <DialogDescription>
              This creates an approval request; the withdrawal posts once another operator approves it.
            </DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={withdrawForm.handleSubmit((values) => {
              setPendingWithdraw(values);
              setWithdrawOpen(false);
              setWithdrawConfirm(true);
            })}
          >
            <FormField control={withdrawForm.control} name="amount" label="Amount" required
              render={({ field, id, describedBy, invalid }) => (
                <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
                  value={field.value ?? ""} onValueChange={field.onChange}
                  onBlur={field.onBlur} name={field.name} ref={field.ref} />
              )} />
            <FormField control={withdrawForm.control} name="payment_account_id" label="Cash / payment GL account" required
              render={({ field, id, describedBy, invalid }) => glSelect(field, id, describedBy, invalid)} />
            <FormField control={withdrawForm.control} name="narration" label="Narration"
              render={({ field, id, describedBy, invalid }) => (
                <Textarea id={id} rows={2} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <div className="flex gap-3">
              <Button type="submit">Request withdrawal</Button>
              <Button type="button" variant="ghost" onClick={() => setWithdrawOpen(false)}>Cancel</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <MakerCheckerConfirmDialog
        open={withdrawConfirm}
        onOpenChange={(o) => { setWithdrawConfirm(o); if (!o) setPendingWithdraw(null); }}
        operationLabel="savings withdrawal"
        subjectLabel={pendingWithdraw?.amount ?? ""}
        busy={withdrawMutation.isPending}
        onConfirm={() => { if (pendingWithdraw) withdrawMutation.mutate(pendingWithdraw); }}
      />
    </div>
  );
}
