// admin/apps/portal/app/platform/(authed)/tenants/[id]/assign-plan/_components/AssignPlanForm.tsx
"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Card,
  DateInput,
  FormField,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  assignPlanSchema,
  type AssignPlanInput,
  type SubscriptionPlanOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function AssignPlanForm({
  tenantId,
  plans,
}: {
  tenantId: string;
  plans: SubscriptionPlanOut[];
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const form = useForm<AssignPlanInput>({
    resolver: zodResolver(assignPlanSchema),
    defaultValues: { plan_id: "" },
  });

  const mutation = useTypedMutation<{ id: string }, AssignPlanInput>(
    async (vars) => {
      // resources.tenants.assignPlan is typed Promise<never>; cast to { data, error }.
      const body = vars.start_date
        ? { plan_id: vars.plan_id, start_date: vars.start_date }
        : { plan_id: vars.plan_id };
      const res = await (
        resources.tenants.assignPlan(tenantId, body) as Promise<{
          data?: { id: string };
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as { id: string };
    },
    {
      invalidates: [queryKeys.billing.subscriptions(), queryKeys.tenants.detail(tenantId)],
      onSuccess: (data) => {
        toast.success("Plan assigned");
        router.push(`/platform/billing/subscriptions/${data.id}`);
      },
      onError: (error) => {
        toast.error("The plan was not assigned", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <Card className="max-w-xl p-6">
    <form
      noValidate
      className="flex flex-col gap-5"
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
    >
      <FormField control={form.control} name="plan_id" label="Plan" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose a plan…" />
            </SelectTrigger>
            <SelectContent>
              {plans.map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="start_date" label="Start date"
        helpText="Optional. Defaults to today if left blank."
        render={({ field, id, describedBy, invalid }) => (
          <DateInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Assign plan</Button>
        <Button type="button" variant="ghost" onClick={() => router.push(`/platform/tenants/${tenantId}`)}>Cancel</Button>
      </div>
    </form>
    </Card>
  );
}
