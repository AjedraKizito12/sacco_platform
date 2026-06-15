// admin/apps/portal/app/platform/(authed)/billing/plans/[id]/edit/_components/EditPlanForm.tsx
"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Checkbox,
  FormField,
  Input,
  MoneyInput,
  ReadOnlyField,
  Textarea,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  subscriptionPlanPatchSchema,
  type SubscriptionPlanOut,
  type SubscriptionPlanPatchInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function EditPlanForm({ plan }: { plan: SubscriptionPlanOut }) {
  const router = useRouter();
  const { resources } = useAuth();
  const form = useForm<SubscriptionPlanPatchInput>({
    resolver: zodResolver(subscriptionPlanPatchSchema),
    defaultValues: {
      name: plan.name,
      description: plan.description ?? "",
      base_price: plan.base_price,
      per_user_price: plan.per_user_price,
      per_member_price: plan.per_member_price,
      trial_period_days: plan.trial_period_days,
      grace_period_days: plan.grace_period_days,
      is_active: plan.is_active,
    },
  });

  const mutation = useTypedMutation<unknown, SubscriptionPlanPatchInput>(
    async (vars) => {
      // resources.billing.patchPlan is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.billing.patchPlan(plan.id, vars as Record<string, unknown>) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [queryKeys.billing.plans(), queryKeys.billing.plan(plan.id)],
      onSuccess: () => {
        toast.success("Changes saved");
        router.push(`/platform/billing/plans/${plan.id}`);
      },
      onError: (error) => {
        toast.error("The plan was not updated", {
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
      <ReadOnlyField label="Code" value={plan.code} />
      <ReadOnlyField label="Currency" value={plan.currency} />
      <ReadOnlyField label="Billing period" value={plan.billing_period} />
      <FormField
        control={form.control}
        name="name"
        label="Name"
        required
        render={({ field, id, describedBy, invalid }) => (
          <Input
            id={id}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            {...field}
          />
        )}
      />
      <FormField
        control={form.control}
        name="description"
        label="Description"
        render={({ field, id, describedBy, invalid }) => (
          <Textarea
            id={id}
            rows={2}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            {...field}
          />
        )}
      />
      <FormField
        control={form.control}
        name="base_price"
        label="Base price"
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput
            id={id}
            currency={plan.currency}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            value={field.value ?? ""}
            onValueChange={field.onChange}
            onBlur={field.onBlur}
            name={field.name}
            ref={field.ref}
          />
        )}
      />
      <FormField
        control={form.control}
        name="per_user_price"
        label="Per-user price"
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput
            id={id}
            currency={plan.currency}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            value={field.value ?? ""}
            onValueChange={field.onChange}
            onBlur={field.onBlur}
            name={field.name}
            ref={field.ref}
          />
        )}
      />
      <FormField
        control={form.control}
        name="per_member_price"
        label="Per-member price"
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput
            id={id}
            currency={plan.currency}
            aria-describedby={describedBy}
            aria-invalid={invalid}
            value={field.value ?? ""}
            onValueChange={field.onChange}
            onBlur={field.onBlur}
            name={field.name}
            ref={field.ref}
          />
        )}
      />
      <FormField
        control={form.control}
        name="trial_period_days"
        label="Trial days"
        render={({ field, id, describedBy, invalid }) => (
          <Input
            id={id}
            type="number"
            inputMode="numeric"
            aria-describedby={describedBy}
            aria-invalid={invalid}
            value={field.value ?? ""}
            onChange={(e) =>
              field.onChange(e.target.value === "" ? undefined : Number(e.target.value))
            }
            onBlur={field.onBlur}
            name={field.name}
            ref={field.ref}
          />
        )}
      />
      <FormField
        control={form.control}
        name="grace_period_days"
        label="Grace days"
        render={({ field, id, describedBy, invalid }) => (
          <Input
            id={id}
            type="number"
            inputMode="numeric"
            aria-describedby={describedBy}
            aria-invalid={invalid}
            value={field.value ?? ""}
            onChange={(e) =>
              field.onChange(e.target.value === "" ? undefined : Number(e.target.value))
            }
            onBlur={field.onBlur}
            name={field.name}
            ref={field.ref}
          />
        )}
      />
      <FormField
        control={form.control}
        name="is_active"
        label="Active"
        render={({ field, id, describedBy }) => (
          <Checkbox
            id={id}
            aria-describedby={describedBy}
            checked={field.value ?? false}
            onCheckedChange={(v) => field.onChange(Boolean(v))}
          />
        )}
      />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>
          Save
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => router.push(`/platform/billing/plans/${plan.id}`)}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
