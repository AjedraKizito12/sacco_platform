"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
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
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import { subscriptionPlanSchema, type SubscriptionPlanInput } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

const CURRENCIES = ["UGX", "KES", "TZS", "RWF", "USD", "EUR", "GBP"] as const;
const PERIODS = ["monthly", "quarterly", "annual"] as const;

export function PlanForm() {
  const router = useRouter();
  const { resources } = useAuth();
  const form = useForm<SubscriptionPlanInput>({
    resolver: zodResolver(subscriptionPlanSchema),
    defaultValues: {
      code: "",
      name: "",
      description: "",
      currency: "UGX",
      base_price: "",
      per_user_price: "0",
      per_member_price: "0",
      billing_period: "monthly",
      features: {},
      trial_period_days: 0,
      grace_period_days: 30,
    },
  });

  const mutation = useTypedMutation<{ id: string }, SubscriptionPlanInput>(
    async (vars) => {
      // resources.billing.createPlan is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.billing.createPlan(vars as Record<string, unknown>) as Promise<{
          data?: { id: string };
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as { id: string };
    },
    {
      invalidates: [queryKeys.billing.plans()],
      onSuccess: (data) => {
        toast.success("Plan created");
        router.push(`/platform/billing/plans/${data.id}`);
      },
      onError: (error) => {
        toast.error("The plan was not created", {
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
      <FormField control={form.control} name="code" label="Code" required
        helpText="Lowercase letters, digits, _ or -. Immutable after creation."
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="name" label="Name" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="description" label="Description"
        render={({ field, id, describedBy, invalid }) => (
          <Textarea id={id} rows={2} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="currency" label="Currency" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CURRENCIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="base_price" label="Base price" required
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            currency={form.watch("currency")}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="per_user_price" label="Per-user price"
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            currency={form.watch("currency")}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="per_member_price" label="Per-member price"
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            currency={form.watch("currency")}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="billing_period" label="Billing period" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PERIODS.map((p) => (
                <SelectItem key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="trial_period_days" label="Trial days"
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} type="number" inputMode="numeric"
            aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""}
            onChange={(e) => field.onChange(e.target.value === "" ? undefined : Number(e.target.value))}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="grace_period_days" label="Grace days"
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} type="number" inputMode="numeric"
            aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""}
            onChange={(e) => field.onChange(e.target.value === "" ? undefined : Number(e.target.value))}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Create plan</Button>
        <Button type="button" variant="ghost" onClick={() => router.push("/platform/billing/plans")}>Cancel</Button>
      </div>
    </form>
  );
}
