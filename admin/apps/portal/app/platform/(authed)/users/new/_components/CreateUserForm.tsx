"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  FormField,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  toast,
} from "@sacco/ui";
import { useTypedMutation, queryKeys } from "@sacco/api-client";
import {
  createPlatformUserSchema,
  PLATFORM_ROLE_OPTIONS,
  type CreatePlatformUserInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function CreateUserForm() {
  const router = useRouter();
  const { resources } = useAuth();
  const form = useForm<CreatePlatformUserInput>({
    resolver: zodResolver(createPlatformUserSchema),
    defaultValues: { email: "", full_name: "", role: "support" },
  });

  const mutation = useTypedMutation<unknown, CreatePlatformUserInput>(
    async (vars) => {
      // resources.admin.createUser is typed Promise<never> because admin.ts
      // uses `as never` on its openapi-fetch paths; cast to the real
      // openapi-fetch { data, error } shape until those resource types tighten
      // (out of SP12 scope).
      const res = await (
        resources.admin.createUser(vars as Record<string, unknown>) as Promise<{
          data?: unknown;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [queryKeys.platformUsers.root()],
      onSuccess: () => {
        toast.success("Platform user created");
        router.push("/platform/users");
      },
      onError: (error) => {
        toast.error("The user was not created", {
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
      <FormField
        control={form.control}
        name="email"
        label="Email"
        required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} type="email" aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )}
      />
      <FormField
        control={form.control}
        name="full_name"
        label="Full name"
        required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )}
      />
      <FormField
        control={form.control}
        name="role"
        label="Role"
        required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger
              id={id}
              aria-describedby={describedBy}
              aria-invalid={invalid}
            >
              <SelectValue placeholder="Select a role" />
            </SelectTrigger>
            <SelectContent>
              {PLATFORM_ROLE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Create user</Button>
        <Button type="button" variant="ghost" onClick={() => router.push("/platform/users")}>Cancel</Button>
      </div>
    </form>
  );
}
