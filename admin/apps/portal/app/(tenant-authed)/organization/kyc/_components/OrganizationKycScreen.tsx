"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Badge,
  Button,
  Card,
  DateInput,
  FormattedDateTime,
  FormField,
  Input,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  ORGANIZATION_KYC_FIELDS,
  organizationKycFormDefaults,
  organizationKycFormSchema,
  toOrganizationKycPayload,
  type OrganizationKycFormInput,
  type OrganizationKycOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";
import { KycCompletionCard } from "@/components/kyc/KycCompletionCard";

export function OrganizationKycScreen({ initial }: { initial: OrganizationKycOut }) {
  const { resources } = useAuth();
  const [latest, setLatest] = useState(initial);

  const form = useForm<OrganizationKycFormInput>({
    resolver: zodResolver(organizationKycFormSchema),
    defaultValues: organizationKycFormDefaults(initial.values),
  });

  // Required-ness is config-driven (platform-owned required set), so it is
  // read from the server-computed completion, not hardcoded per field.
  const requiredByKey = new Map(
    latest.completion.items.map((item) => [item.key, item.required]),
  );

  const mutation = useTypedMutation<OrganizationKycOut, OrganizationKycFormInput>(
    async (vars) => {
      // putKyc is typed Promise<never> (as-never paths); cast to the real
      // { data, error } shape, same as every other resource call site.
      const res = await (resources.organization.putKyc(
        toOrganizationKycPayload(vars),
      ) as Promise<{ data?: OrganizationKycOut; error?: unknown }>);
      if (res.error || !res.data) throw res.error ?? new Error("Empty response");
      return res.data;
    },
    {
      invalidates: [queryKeys.organization.root()],
      onSuccess: (data) => {
        const verificationReset = latest.verified && !data.verified;
        setLatest(data);
        form.reset(organizationKycFormDefaults(data.values));
        toast.success(
          "Organization KYC saved",
          verificationReset
            ? {
                description:
                  "Your changes reset platform verification — the platform team must re-verify.",
              }
            : undefined,
        );
      },
      onError: (error) => {
        toast.error("Organization KYC was not saved", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <h1 className="text-[var(--text-h3)] font-semibold">Organization KYC</h1>
        {latest.verified ? (
          <Badge variant="success">Verified by platform</Badge>
        ) : (
          <Badge variant="neutral">Not verified</Badge>
        )}
        {latest.verified && latest.verified_at ? (
          <span className="text-[13px] text-[var(--text-secondary)]">
            since <FormattedDateTime value={latest.verified_at} />
          </span>
        ) : null}
      </div>
      <p className="max-w-2xl text-[13px] text-[var(--text-secondary)]">
        Self-attested registration and regulatory details for this SACCO. Completion is
        informational — it does not block any operation. Verification is set by the
        platform team once all required items are complete.
      </p>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card className="self-start p-6">
        <form
          noValidate
          className="flex flex-col gap-5"
          onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
        >
          {ORGANIZATION_KYC_FIELDS.map((spec) => (
            <FormField
              key={spec.key}
              control={form.control}
              name={spec.key}
              label={spec.label}
              required={requiredByKey.get(spec.key) ?? false}
              render={({ field, id, describedBy, invalid }) =>
                spec.kind === "date" ? (
                  <DateInput
                    id={id}
                    aria-describedby={describedBy}
                    aria-invalid={invalid}
                    value={field.value}
                    onValueChange={field.onChange}
                    onBlur={field.onBlur}
                  />
                ) : (
                  <Input
                    id={id}
                    type={spec.kind === "email" ? "email" : "text"}
                    aria-describedby={describedBy}
                    aria-invalid={invalid}
                    {...field}
                  />
                )
              }
            />
          ))}
          <div>
            <Button type="submit" disabled={mutation.isPending}>
              Save organization KYC
            </Button>
          </div>
        </form>
        </Card>

        <div className="lg:sticky lg:top-6 lg:self-start">
          <KycCompletionCard completion={latest.completion} />
        </div>
      </div>
    </div>
  );
}
