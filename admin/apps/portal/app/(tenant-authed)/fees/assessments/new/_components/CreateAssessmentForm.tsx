// admin/apps/portal/app/(tenant-authed)/fees/assessments/new/_components/CreateAssessmentForm.tsx
"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  DateInput,
  FormField,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  toast,
} from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import {
  feeAssessmentSchema,
  type FeeAssessmentInput,
  type FeeAssessmentOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface TargetOption {
  id: string;
  label: string;
}
export type TargetMap = Record<
  "member" | "loan" | "savings_account" | "share_account",
  TargetOption[]
>;
export interface FeeTypeOption {
  id: string;
  code: string;
  name: string;
}

export function CreateAssessmentForm({
  feeTypes,
  targets,
}: {
  feeTypes: FeeTypeOption[];
  targets: TargetMap;
}) {
  const router = useRouter();
  const { resources } = useAuth();

  const form = useForm<FeeAssessmentInput>({
    resolver: zodResolver(feeAssessmentSchema),
    defaultValues: {
      fee_type_id: "",
      target_type: "member",
      target_id: "",
      period_start: "",
      period_end: "",
    },
  });

  const targetType = form.watch("target_type") as keyof TargetMap;
  const targetOptions = targets[targetType] ?? [];

  const mutation = useTypedMutation<FeeAssessmentOut, FeeAssessmentInput>(
    async (vars) => {
      const body: Record<string, unknown> = { ...vars };
      if (!body["period_end"]) delete body["period_end"];
      const res = await (
        resources.fees.createAssessment(body) as Promise<{
          data?: FeeAssessmentOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as FeeAssessmentOut;
    },
    {
      onSuccess: (data) => {
        toast.success("Assessment created");
        router.push(`/fees/assessments/${data.id}`);
      },
      onError: (error) => {
        toast.error("The assessment was not created", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <form
      noValidate
      className="flex max-w-xl flex-col gap-5"
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
    >
      <FormField control={form.control} name="fee_type_id" label="Fee type" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose a fee type…" />
            </SelectTrigger>
            <SelectContent>
              {feeTypes.map((t) => (
                <SelectItem key={t.id} value={t.id}>{t.code} — {t.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="target_type" label="Target type" required
        render={({ field, id, describedBy, invalid }) => (
          <Select
            value={field.value}
            onValueChange={(v) => {
              field.onChange(v);
              form.setValue("target_id", "");
            }}
          >
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="member">Member</SelectItem>
              <SelectItem value="loan">Loan</SelectItem>
              <SelectItem value="savings_account">Savings account</SelectItem>
              <SelectItem value="share_account">Share account</SelectItem>
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="target_id" label="Target record" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose a target…" />
            </SelectTrigger>
            <SelectContent>
              {targetOptions.map((o) => (
                <SelectItem key={o.id} value={o.id}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="period_start" label="Period start" required
        render={({ field, id, describedBy, invalid }) => (
          <DateInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="period_end" label="Period end (optional)"
        render={({ field, id, describedBy, invalid }) => (
          <DateInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Create assessment</Button>
        <Button type="button" variant="ghost" onClick={() => router.push("/fees/assessments")}>Cancel</Button>
      </div>
    </form>
  );
}
