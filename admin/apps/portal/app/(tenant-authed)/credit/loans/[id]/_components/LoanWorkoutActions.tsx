// admin/apps/portal/app/(tenant-authed)/credit/loans/[id]/_components/LoanWorkoutActions.tsx
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
  loanRecoverySchema,
  loanRestructureSchema,
  loanWriteOffSchema,
  type LoanRecoveryInput,
  type LoanRecoveryOut,
  type LoanRestructureInput,
  type LoanWriteOffInput,
  type WriteOffOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface GlAccountOption {
  id: string;
  code: string;
  name: string;
  account_type: string;
}

export function LoanWorkoutActions({
  loanId,
  status,
  glAccounts,
}: {
  loanId: string;
  status: string;
  glAccounts: GlAccountOption[];
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const isWrittenOff = status === "written_off";

  const [writeOffOpen, setWriteOffOpen] = useState(false);
  const [restructureOpen, setRestructureOpen] = useState(false);
  const [recoverOpen, setRecoverOpen] = useState(false);

  const [writeOffKey] = useState(() => crypto.randomUUID());
  const [restructureKey] = useState(() => crypto.randomUUID());
  const [recoverKey] = useState(() => crypto.randomUUID());

  const writeOffForm = useForm<LoanWriteOffInput>({
    resolver: zodResolver(loanWriteOffSchema),
    defaultValues: { amount: "", reason: "", loan_loss_account_code: "", idempotency_key: writeOffKey },
  });
  const restructureForm = useForm<LoanRestructureInput>({
    resolver: zodResolver(loanRestructureSchema),
    defaultValues: { restructuring_type: "term_extension", periods_added: "", reason: "", idempotency_key: restructureKey },
  });
  const recoverForm = useForm<LoanRecoveryInput>({
    resolver: zodResolver(loanRecoverySchema),
    defaultValues: { amount: "", reason: "", idempotency_key: recoverKey },
  });

  const writeOffMutation = useTypedMutation<WriteOffOut, LoanWriteOffInput>(
    async (vars) => {
      const body: Record<string, unknown> = { ...vars };
      if (!body["loan_loss_account_code"]) delete body["loan_loss_account_code"];
      const res = await (
        resources.credit.writeOff(loanId, body) as Promise<{ data?: WriteOffOut; error?: unknown }>
      );
      if (res.error) throw res.error;
      return res.data as WriteOffOut;
    },
    {
      onSuccess: (data) => {
        toast.success(
          data.direct ? "Loan written off" : "Write-off requested — pending approval (2 required)",
        );
        setWriteOffOpen(false);
        router.refresh();
      },
      onError: (error) => {
        toast.error("The write-off failed", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const restructureMutation = useTypedMutation<unknown, LoanRestructureInput>(
    async (vars) => {
      const res = await (
        resources.credit.restructure(loanId, vars) as Promise<{ data?: unknown; error?: unknown }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      onSuccess: () => {
        toast.success("Restructuring requested — pending approval (2 required)");
        setRestructureOpen(false);
        router.refresh();
      },
      onError: (error) => {
        toast.error("The restructuring failed", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const recoverMutation = useTypedMutation<LoanRecoveryOut, LoanRecoveryInput>(
    async (vars) => {
      const res = await (
        resources.credit.recover(loanId, vars) as Promise<{ data?: LoanRecoveryOut; error?: unknown }>
      );
      if (res.error) throw res.error;
      return res.data as LoanRecoveryOut;
    },
    {
      onSuccess: () => {
        toast.success("Recovery posted");
        setRecoverOpen(false);
        router.refresh();
      },
      onError: (error) => {
        toast.error("The recovery failed", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <div className="flex items-center gap-2">
      {isWrittenOff ? (
        <Button variant="secondary" onClick={() => setRecoverOpen(true)}>Recover</Button>
      ) : (
        <>
          <Button variant="secondary" onClick={() => setWriteOffOpen(true)}>Write off</Button>
          <Button variant="secondary" onClick={() => setRestructureOpen(true)}>Restructure</Button>
        </>
      )}

      {/* Write-off */}
      <Dialog open={writeOffOpen} onOpenChange={(o) => { if (!o) setWriteOffOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Write off loan</DialogTitle>
            <DialogDescription>
              At or above the product&apos;s write-off threshold this creates a maker-checker
              approval (quorum 2); otherwise it posts immediately.
            </DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={writeOffForm.handleSubmit((values) => writeOffMutation.mutate(values))}
          >
            <FormField control={writeOffForm.control} name="amount" label="Amount" required
              render={({ field, id, describedBy, invalid }) => (
                <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
                  value={field.value ?? ""} onValueChange={field.onChange}
                  onBlur={field.onBlur} name={field.name} ref={field.ref} />
              )} />
            <FormField control={writeOffForm.control} name="reason" label="Reason" required
              render={({ field, id, describedBy, invalid }) => (
                <Textarea id={id} rows={3} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <FormField control={writeOffForm.control} name="loan_loss_account_code" label="Loan-loss GL account"
              render={({ field, id, describedBy, invalid }) => (
                <Select value={field.value ?? ""} onValueChange={field.onChange}>
                  <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
                    <SelectValue placeholder="Default (product setting)…" />
                  </SelectTrigger>
                  <SelectContent>
                    {glAccounts.map((a) => (
                      <SelectItem key={a.id} value={a.code}>{a.code} — {a.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )} />
            <div className="flex gap-3">
              <Button type="submit" disabled={writeOffMutation.isPending}>Post write-off</Button>
              <Button type="button" variant="ghost" onClick={() => setWriteOffOpen(false)}>Cancel</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Restructure */}
      <Dialog open={restructureOpen} onOpenChange={(o) => { if (!o) setRestructureOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Restructure loan</DialogTitle>
            <DialogDescription>This creates a maker-checker approval (quorum 2).</DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={restructureForm.handleSubmit((values) => restructureMutation.mutate(values))}
          >
            <FormField control={restructureForm.control} name="restructuring_type" label="Type" required
              render={({ field, id, describedBy, invalid }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
                    <SelectValue placeholder="Choose…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="term_extension">Term extension</SelectItem>
                    <SelectItem value="payment_holiday">Payment holiday</SelectItem>
                  </SelectContent>
                </Select>
              )} />
            <FormField control={restructureForm.control} name="periods_added" label="Periods added" required
              render={({ field, id, describedBy, invalid }) => (
                <Input id={id} inputMode="numeric" aria-describedby={describedBy}
                  aria-invalid={invalid} {...field} />
              )} />
            <FormField control={restructureForm.control} name="reason" label="Reason" required
              render={({ field, id, describedBy, invalid }) => (
                <Textarea id={id} rows={3} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <div className="flex gap-3">
              <Button type="submit" disabled={restructureMutation.isPending}>Request restructuring</Button>
              <Button type="button" variant="ghost" onClick={() => setRestructureOpen(false)}>Cancel</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Recover */}
      <Dialog open={recoverOpen} onOpenChange={(o) => { if (!o) setRecoverOpen(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Recover written-off loan</DialogTitle>
            <DialogDescription>Post a recovery against this written-off loan.</DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-4"
            onSubmit={recoverForm.handleSubmit((values) => recoverMutation.mutate(values))}
          >
            <FormField control={recoverForm.control} name="amount" label="Amount" required
              render={({ field, id, describedBy, invalid }) => (
                <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
                  value={field.value ?? ""} onValueChange={field.onChange}
                  onBlur={field.onBlur} name={field.name} ref={field.ref} />
              )} />
            <FormField control={recoverForm.control} name="reason" label="Reason" required
              render={({ field, id, describedBy, invalid }) => (
                <Textarea id={id} rows={3} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
              )} />
            <div className="flex gap-3">
              <Button type="submit" disabled={recoverMutation.isPending}>Post recovery</Button>
              <Button type="button" variant="ghost" onClick={() => setRecoverOpen(false)}>Cancel</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
