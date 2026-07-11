"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Card,
  Checkbox,
  FormField,
  Input,
  MakerCheckerConfirmDialog,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  toast,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  updatePlatformUserSchema,
  PLATFORM_ROLE_OPTIONS,
  type PlatformUserOut,
  type UpdatePlatformUserInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

/** is_active / role changes route through maker-checker on the backend. */
function isSensitiveChange(
  user: PlatformUserOut,
  values: Pick<UpdatePlatformUserInput, "is_active" | "role">,
): boolean {
  return values.is_active !== user.is_active || values.role !== user.role;
}

export function EditUserForm({ user }: { user: PlatformUserOut }) {
  const router = useRouter();
  const { resources } = useAuth();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, setPending] = useState<UpdatePlatformUserInput | null>(null);

  const form = useForm<UpdatePlatformUserInput>({
    resolver: zodResolver(updatePlatformUserSchema),
    defaultValues: {
      full_name: user.full_name,
      is_active: user.is_active,
      role: user.role,
    },
  });

  const mutation = useTypedMutation<unknown, UpdatePlatformUserInput>(
    async (vars) => {
      // resources.admin.patchUser is typed Promise<never> because admin.ts
      // uses `as never` on its openapi-fetch paths; cast to the real
      // { data, error } shape until those resource types tighten (out of SP12 scope).
      const res = await (
        resources.admin.patchUser(user.id, vars as Record<string, unknown>) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [
        queryKeys.platformUsers.root(),
        queryKeys.platformUsers.detail(user.id),
      ],
      onSuccess: (_data, vars) => {
        if (isSensitiveChange(user, vars)) {
          toast.success("Approval request created", {
            description:
              "The change will apply once another platform user approves it.",
          });
        } else {
          toast.success("Changes saved");
        }
        setConfirmOpen(false);
        setPending(null);
        router.push(`/platform/users/${user.id}`);
      },
      onError: (error) => {
        toast.error("The change was not saved", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  // Drives the dual-mode submit label: sensitive changes create an approval
  // request (contract K: label "Request X", not "X"); name-only saves directly.
  const sensitiveDirty = isSensitiveChange(user, {
    is_active: form.watch("is_active"),
    role: form.watch("role"),
  });

  function onValid(values: UpdatePlatformUserInput) {
    if (isSensitiveChange(user, values)) {
      setPending(values);
      setConfirmOpen(true);
      return;
    }
    mutation.mutate(values);
  }

  return (
    <>
      <Card className="max-w-xl p-6">
      <form
        className="flex flex-col gap-5"
        onSubmit={form.handleSubmit(onValid)}
        noValidate
      >
        <FormField
          control={form.control}
          name="full_name"
          label="Full name"
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
          name="role"
          label="Role"
          required
          helpText="Changing the role creates an approval request."
          render={({ field, id, describedBy, invalid }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger
                id={id}
                aria-describedby={describedBy}
                aria-invalid={invalid}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PLATFORM_ROLE_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />
        <FormField
          control={form.control}
          name="is_active"
          label="Active"
          helpText="Deactivating a user creates an approval request."
          render={({ field, id, describedBy }) => (
            <Checkbox
              id={id}
              aria-describedby={describedBy}
              checked={field.value}
              onCheckedChange={(v) => field.onChange(Boolean(v))}
            />
          )}
        />
        <div className="flex gap-3">
          <Button type="submit" disabled={mutation.isPending}>
            {sensitiveDirty ? "Request Change" : "Save"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => router.push(`/platform/users/${user.id}`)}
          >
            Cancel
          </Button>
        </div>
      </form>
      </Card>

      <MakerCheckerConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        operationLabel="platform user change"
        subjectLabel={user.email}
        busy={mutation.isPending}
        onConfirm={() => {
          if (pending) mutation.mutate(pending);
        }}
      />
    </>
  );
}
