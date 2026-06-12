"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Card,
  FormField,
  Input,
  StatusBadge,
  Stepper,
  toast,
} from "@sacco/ui";
import { useTypedMutation, queryKeys } from "@sacco/api-client";
import {
  createTenantSchema,
  suggestSlug,
  type CreateTenantInput,
  type TenantOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";
import { useTenantProvisioning } from "@/hooks/use-tenant-provisioning";

const WIZARD_STEPS = [
  { id: "details", label: "Details" },
  { id: "provisioning", label: "Provisioning" },
  { id: "done", label: "Done" },
];

interface CreateTenantResponse {
  tenant: TenantOut;
  status_url: string;
}

export function NewTenantWizard() {
  const { resources } = useAuth();
  const [provisioningTenant, setProvisioningTenant] = useState<TenantOut | null>(null);
  const slugEditedRef = useRef(false);

  const form = useForm<CreateTenantInput>({
    resolver: zodResolver(createTenantSchema),
    defaultValues: { slug: "", name: "", admin_email: "" },
  });

  const mutation = useTypedMutation<CreateTenantResponse, CreateTenantInput>(
    async (vars) => {
      // Backend treats admin_email as optional; "" means "no seed admin" —
      // strip it so the wire payload omits the key (exactOptionalPropertyTypes).
      const body = {
        slug: vars.slug,
        name: vars.name,
        ...(vars.admin_email ? { admin_email: vars.admin_email } : {}),
      };
      // resources.tenants.create is typed Promise<never> because tenants.ts
      // uses `as never` on its openapi-fetch paths; cast to the real
      // { data, error } shape until those resource types tighten.
      const res = await (
        resources.tenants.create(body) as Promise<{
          data?: CreateTenantResponse;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      if (!res.data) throw new Error("Empty provisioning response");
      return res.data;
    },
    {
      invalidates: [queryKeys.tenants.root()],
      onSuccess: (data) => setProvisioningTenant(data.tenant),
      onError: (error) => {
        toast.error("The tenant was not created", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  // Keep the slug suggestion in sync with the name until the operator touches
  // the slug field. A useRef latch (slugEditedRef) is used instead of
  // dirtyFields.slug because clearing the slug field resets dirtyFields.slug
  // to false (value matches defaultValue ""), which would allow name edits to
  // re-suggest the slug even after the operator has intentionally cleared it.
  function onNameChange(name: string) {
    if (!slugEditedRef.current) {
      form.setValue("slug", suggestSlug(name));
    }
  }

  if (provisioningTenant) {
    return <ProvisioningProgress tenant={provisioningTenant} />;
  }

  return (
    <div className="flex max-w-xl flex-col gap-6">
      <Stepper steps={WIZARD_STEPS} currentStepId="details" />
      <form
        noValidate
        className="flex flex-col gap-5"
        onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
      >
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
              onChange={(e) => {
                field.onChange(e);
                onNameChange(e.target.value);
              }}
            />
          )}
        />
        <FormField
          control={form.control}
          name="slug"
          label="Slug"
          required
          helpText="URL-safe identifier. Immutable after creation."
          render={({ field, id, describedBy, invalid }) => (
            <Input
              id={id}
              aria-describedby={describedBy}
              aria-invalid={invalid}
              {...field}
              onChange={(e) => {
                slugEditedRef.current = true;
                field.onChange(e);
              }}
            />
          )}
        />
        <FormField
          control={form.control}
          name="admin_email"
          label="Initial admin email"
          helpText="Optional. Seeds an admin user who sets their password via the reset flow."
          render={({ field, id, describedBy, invalid }) => (
            <Input id={id} type="email" aria-describedby={describedBy} aria-invalid={invalid} {...field} />
          )}
        />
        <div>
          <Button type="submit" disabled={mutation.isPending}>
            Provision tenant
          </Button>
        </div>
      </form>
    </div>
  );
}

function ProvisioningProgress({ tenant }: { tenant: TenantOut }) {
  // Drop initialData here so TanStack fires a fresh fetch on mount rather than
  // seeding with stale provisioning state. The created tenant is kept as a
  // local first-paint fallback only (`current = live.data ?? tenant`) so the
  // UI is never blank between mutation success and the first GET response.
  // (Passing initialData without initialDataUpdatedAt is marked stale at t=0
  // and does trigger an immediate background refetch, but that behaviour is
  // not reliably observable in jsdom tests where microtask timing differs from
  // a real browser. Dropping initialData keeps the refetch deterministic and
  // the tests honest.)
  const live = useTenantProvisioning(tenant.id);
  const current = live.data ?? tenant;

  const stepId = current.status === "active" ? "done" : "provisioning";

  return (
    <div className="flex max-w-xl flex-col gap-6">
      <Stepper steps={WIZARD_STEPS} currentStepId={stepId} />
      <Card className="flex flex-col gap-4 p-6">
        <div className="flex items-center gap-3">
          <h2 className="text-[var(--text-h5)] font-semibold">{current.name}</h2>
          <StatusBadge entity="tenant" status={current.status} />
        </div>

        {current.status === "active" ? (
          <>
            <p className="text-[var(--text-secondary)]">Tenant is ready.</p>
            <div>
              <Button asChild>
                <Link href={`/platform/tenants/${current.id}`}>View tenant</Link>
              </Button>
            </div>
          </>
        ) : current.status === "failed" ? (
          <div role="alert">
            <p className="text-[var(--text-secondary)]">
              Provisioning failed
              {current.failed_step ? ` at step "${current.failed_step}"` : ""}.
            </p>
            {current.failure_reason ? (
              <p className="text-[var(--text-danger)]">{current.failure_reason}</p>
            ) : null}
            <p className="text-[var(--text-secondary)]">
              Open the tenant to request a provisioning retry.
            </p>
            <div>
              <Button asChild variant="secondary">
                <Link href={`/platform/tenants/${current.id}`}>Open tenant</Link>
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-[var(--text-secondary)]" aria-live="polite">
            Provisioning in progress
            {current.provisioning_state ? ` — ${current.provisioning_state}` : ""}…
            This page updates automatically.
          </p>
        )}
      </Card>
    </div>
  );
}
