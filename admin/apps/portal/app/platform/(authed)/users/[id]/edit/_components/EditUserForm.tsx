"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Checkbox,
  FormField,
  Input,
  MakerCheckerConfirmDialog,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  updatePlatformUserSchema,
  type PlatformRole,
  type PlatformUserOut,
  type UpdatePlatformUserInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";

const ROLE_OPTIONS: { value: PlatformRole; label: string }[] = [
  { value: "support", label: "Support" },
  { value: "finance", label: "Finance" },
  { value: "admin", label: "Admin" },
  { value: "superuser", label: "Superuser" },
];

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
      onSuccess: () => {
        setConfirmOpen(false);
        setPending(null);
        router.push(`/platform/users/${user.id}`);
      },
    },
  );

  function onValid(values: UpdatePlatformUserInput) {
    const sensitiveDirty =
      values.is_active !== user.is_active || values.role !== user.role;
    if (sensitiveDirty) {
      setPending(values);
      setConfirmOpen(true);
      return;
    }
    mutation.mutate(values);
  }

  return (
    <>
      <form
        className="flex max-w-xl flex-col gap-5"
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
          render={({ field, id }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger id={id} aria-label="Role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLE_OPTIONS.map((o) => (
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
          render={({ field, id }) => (
            <Checkbox
              id={id}
              checked={field.value}
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
            onClick={() => router.push(`/platform/users/${user.id}`)}
          >
            Cancel
          </Button>
        </div>
      </form>

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
