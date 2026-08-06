"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Card,
  ConfirmDialog,
  Count,
  DateInput,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  FormattedDateTime,
  FormField,
  MakerCheckerConfirmDialog,
  ReadOnlyField,
  StatusBadge,
  Textarea,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  extendRetentionSchema,
  tenantCancelSchema,
  type ExtendRetentionInput,
  type TenantCancelInput,
  type TenantLifecycleEventOut,
  type TenantOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

// Restore is allowed only while the schema is still present (not yet physically
// archived). Mirrors OffboardingService.restore's guard.
const RESTORABLE = new Set(["cancelled", "read_only", "archived"]);

function CancelTenantDialog({
  tenant,
  onDone,
}: {
  tenant: TenantOut;
  onDone(): void;
}) {
  const { resources } = useAuth();
  const [formOpen, setFormOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, setPending] = useState<TenantCancelInput | null>(null);

  const form = useForm<TenantCancelInput>({
    resolver: zodResolver(tenantCancelSchema),
    defaultValues: { reason: "" },
  });

  const mutation = useTypedMutation<unknown, TenantCancelInput>(
    async (vars) => {
      const res = await (resources.tenants.cancel(tenant.id, vars) as Promise<{
        data?: unknown;
        error?: unknown;
      }>);
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [queryKeys.tenants.root(), queryKeys.tenants.detail(tenant.id)],
      onSuccess: () => {
        toast.success("Approval request created", {
          description:
            "The tenant will be cancelled once another platform user approves it.",
        });
        setConfirmOpen(false);
        setFormOpen(false);
        setPending(null);
        form.reset();
        onDone();
      },
      onError: (error) => {
        toast.error("The cancellation was not requested", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <>
      <Button variant="destructive" onClick={() => setFormOpen(true)}>
        Request Cancellation
      </Button>

      <Dialog open={formOpen} onOpenChange={setFormOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancel {tenant.name}</DialogTitle>
            <DialogDescription>
              Cancellation begins offboarding: the tenant loses write access and
              billing is stopped. It is reversible until the account is
              physically archived.
            </DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-5"
            onSubmit={form.handleSubmit((values) => {
              setPending(values);
              setFormOpen(false);
              setConfirmOpen(true);
            })}
          >
            <FormField
              control={form.control}
              name="reason"
              label="Reason"
              required
              helpText="Recorded on the approval request and the audit log. Minimum 10 characters."
              render={({ field, id, describedBy, invalid }) => (
                <Textarea
                  id={id}
                  rows={3}
                  aria-describedby={describedBy}
                  aria-invalid={invalid}
                  {...field}
                />
              )}
            />
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setFormOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" variant="destructive">
                Continue
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <MakerCheckerConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        operationLabel="tenant cancellation"
        subjectLabel={tenant.name}
        busy={mutation.isPending}
        onConfirm={() => {
          if (pending) mutation.mutate(pending);
        }}
      />
    </>
  );
}

function RestoreButton({
  tenant,
  onDone,
}: {
  tenant: TenantOut;
  onDone(): void;
}) {
  const { resources } = useAuth();
  const [open, setOpen] = useState(false);

  const mutation = useTypedMutation<unknown, void>(
    async () => {
      const res = await (resources.tenants.restore(tenant.id) as Promise<{
        data?: unknown;
        error?: unknown;
      }>);
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [queryKeys.tenants.root(), queryKeys.tenants.detail(tenant.id)],
      onSuccess: () => {
        toast.success("Tenant restored to active");
        setOpen(false);
        onDone();
      },
      onError: (error) => {
        toast.error("The tenant was not restored", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>
        Restore
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={`Restore ${tenant.name}?`}
        description="This returns the tenant to active immediately. No approval is required. Re-assign a plan separately to resume billing."
        confirmLabel="Restore tenant"
        busy={mutation.isPending}
        onConfirm={() => mutation.mutate()}
      />
    </>
  );
}

function ExtendRetentionDialog({
  tenant,
  onDone,
}: {
  tenant: TenantOut;
  onDone(): void;
}) {
  const { resources } = useAuth();
  const [open, setOpen] = useState(false);

  const form = useForm<ExtendRetentionInput>({
    resolver: zodResolver(extendRetentionSchema),
    defaultValues: { hold_until: "" },
  });

  const mutation = useTypedMutation<unknown, ExtendRetentionInput>(
    async (vars) => {
      // The API takes an ISO datetime; the date input yields YYYY-MM-DD.
      const hold_until = new Date(`${vars.hold_until}T00:00:00Z`).toISOString();
      const res = await (resources.tenants.extendRetention(tenant.id, {
        hold_until,
      }) as Promise<{ data?: unknown; error?: unknown }>);
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [queryKeys.tenants.root(), queryKeys.tenants.detail(tenant.id)],
      onSuccess: () => {
        toast.success("Retention extended");
        setOpen(false);
        form.reset();
        onDone();
      },
      onError: (error) => {
        toast.error("Retention was not extended", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Extend retention
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Extend retention for {tenant.name}</DialogTitle>
            <DialogDescription>
              A legal hold pauses automatic archival until the chosen date.
            </DialogDescription>
          </DialogHeader>
          <form
            noValidate
            className="flex flex-col gap-5"
            onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
          >
            <FormField
              control={form.control}
              name="hold_until"
              label="Hold until"
              required
              render={({ field, id, describedBy, invalid }) => (
                <DateInput
                  id={id}
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
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={mutation.isPending}>
                Extend
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}

function LifecycleTimeline({ events }: { events: TenantLifecycleEventOut[] }) {
  if (events.length === 0) {
    return (
      <p className="text-[13px] text-[var(--text-muted)]">
        No lifecycle events yet.
      </p>
    );
  }
  return (
    <ol className="flex flex-col gap-3">
      {[...events].reverse().map((e) => (
        <li key={e.id} className="flex items-center gap-3">
          <StatusBadge entity="tenant_lifecycle" status={e.to_state} />
          <span className="text-[13px] text-[var(--text-muted)]">
            from {e.from_state}
          </span>
          <FormattedDateTime value={e.occurred_at} />
          {e.reason ? (
            <span className="text-[13px]">— {e.reason}</span>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

export function OffboardingSection({
  tenant,
  events,
  canOffboard,
}: {
  tenant: TenantOut;
  events: TenantLifecycleEventOut[];
  canOffboard: boolean;
}) {
  const router = useRouter();
  const refresh = () => router.refresh();
  const isActive = tenant.lifecycle_state === "active";
  const isPhysicallyArchived = tenant.archive_checksum !== null;
  const canRestore =
    canOffboard && RESTORABLE.has(tenant.lifecycle_state) && !isPhysicallyArchived;

  return (
    <Card className="flex flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-[var(--text-h5)] font-semibold">Offboarding</h2>
          <StatusBadge entity="tenant_lifecycle" status={tenant.lifecycle_state} />
        </div>
        {canOffboard ? (
          <div className="flex items-center gap-2">
            {isActive ? (
              <CancelTenantDialog tenant={tenant} onDone={refresh} />
            ) : null}
            {canRestore ? <RestoreButton tenant={tenant} onDone={refresh} /> : null}
            {!isActive ? (
              <ExtendRetentionDialog tenant={tenant} onDone={refresh} />
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-5">
        <ReadOnlyField
          label="Cancelled"
          value={
            tenant.cancelled_at ? (
              <FormattedDateTime value={tenant.cancelled_at} />
            ) : (
              "—"
            )
          }
        />
        <ReadOnlyField
          label="Read-only since"
          value={
            tenant.read_only_at ? (
              <FormattedDateTime value={tenant.read_only_at} />
            ) : (
              "—"
            )
          }
        />
        <ReadOnlyField
          label="Archived"
          value={
            tenant.archived_at ? (
              <FormattedDateTime value={tenant.archived_at} />
            ) : (
              "—"
            )
          }
        />
        <ReadOnlyField
          label="Retention hold until"
          value={
            tenant.retention_hold_until ? (
              <FormattedDateTime value={tenant.retention_hold_until} />
            ) : (
              "—"
            )
          }
        />
        {isPhysicallyArchived ? (
          <>
            <ReadOnlyField
              label="Archive size"
              value={
                tenant.archive_size_bytes !== null ? (
                  <Count value={tenant.archive_size_bytes} /> // bytes
                ) : (
                  "—"
                )
              }
            />
            <ReadOnlyField
              label="Archive key"
              value={tenant.archive_storage_key ?? "—"}
            />
          </>
        ) : null}
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-[13px] font-semibold text-[var(--text-muted)]">
          Lifecycle timeline
        </h3>
        <LifecycleTimeline events={events} />
      </div>
    </Card>
  );
}
