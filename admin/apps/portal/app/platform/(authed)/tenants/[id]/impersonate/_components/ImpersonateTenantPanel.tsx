"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Card,
  FormattedDateTime,
  FormField,
  MakerCheckerConfirmDialog,
  Textarea,
  toast,
} from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import {
  impersonationRequestSchema,
  type ImpersonationRequestInput,
  type TenantOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface ActiveImpersonation {
  id: string;
  expires_at: string;
}

export function ImpersonateTenantPanel({
  tenant,
  activeForTenant,
}: {
  tenant: TenantOut;
  activeForTenant: ActiveImpersonation[];
}) {
  const { resources } = useAuth();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, setPending] = useState<ImpersonationRequestInput | null>(null);
  const [entering, setEntering] = useState<string | null>(null);

  const form = useForm<ImpersonationRequestInput>({
    resolver: zodResolver(impersonationRequestSchema),
    defaultValues: { reason: "" },
  });

  const requestMutation = useTypedMutation<unknown, ImpersonationRequestInput>(
    async (vars) => {
      // resources.impersonations.request is typed Promise<never>; cast to { data, error }.
      const res = await (
        resources.impersonations.request({ tenant_id: tenant.id, reason: vars.reason }) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      onSuccess: () => {
        toast.success("Approval request created", {
          description: "Another platform user must approve before you can enter the tenant session.",
        });
        setConfirmOpen(false);
        setPending(null);
        form.reset();
      },
      onError: (error) => {
        toast.error("The impersonation was not requested", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  async function enterSession(impersonationId: string) {
    setEntering(impersonationId);
    try {
      const res = await fetch("/api/impersonation/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          impersonation_id: impersonationId,
          tenant_id: tenant.id,
          tenant_name: tenant.name,
        }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: string } | null;
        toast.error("Couldn’t enter the tenant session", {
          description: apiErrorMessage(body, "The session may have expired. Request a new one."),
        });
        return;
      }
      // Full-page navigation so middleware re-resolves into the tenant context
      // (the tenant slug cookie is now set).
      window.location.assign("/");
    } finally {
      setEntering(null);
    }
  }

  return (
    <div className="flex max-w-xl flex-col gap-6">
      {activeForTenant.length > 0 ? (
        <Card className="flex flex-col gap-3 p-6">
          <h2 className="text-[var(--text-h5)] font-semibold">Approved sessions</h2>
          {activeForTenant.map((imp) => (
            <div key={imp.id} className="flex items-center justify-between gap-4">
              <span className="text-[var(--text-secondary)]">
                Expires <FormattedDateTime value={imp.expires_at} />
              </span>
              <Button
                variant="primary"
                disabled={entering !== null}
                onClick={() => void enterSession(imp.id)}
              >
                Enter session
              </Button>
            </div>
          ))}
        </Card>
      ) : null}

      <Card className="flex flex-col gap-4 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Request impersonation</h2>
        <p className="text-[var(--text-secondary)]">
          Impersonation requires approval from another platform user and is
          time-limited. All actions during the session are audited as yours.
        </p>
        <form
          noValidate
          className="flex flex-col gap-5"
          onSubmit={form.handleSubmit((values) => {
            setPending(values);
            setConfirmOpen(true);
          })}
        >
          <FormField
            control={form.control}
            name="reason"
            label="Reason"
            required
            helpText="Recorded on the approval request and the audit trail. Minimum 10 characters."
            render={({ field, id, describedBy, invalid }) => (
              <Textarea id={id} rows={3} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
            )}
          />
          <div>
            <Button type="submit" disabled={requestMutation.isPending}>
              Request Impersonation
            </Button>
          </div>
        </form>
      </Card>

      <MakerCheckerConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        operationLabel="tenant impersonation"
        subjectLabel={tenant.name}
        busy={requestMutation.isPending}
        onConfirm={() => {
          if (pending) requestMutation.mutate(pending);
        }}
      />
    </div>
  );
}
