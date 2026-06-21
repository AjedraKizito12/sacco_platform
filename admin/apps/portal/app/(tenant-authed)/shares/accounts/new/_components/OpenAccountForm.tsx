// admin/apps/portal/app/(tenant-authed)/shares/accounts/new/_components/OpenAccountForm.tsx
"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  FormField,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  toast,
} from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import {
  openShareAccountSchema,
  type OpenShareAccountInput,
  type ShareAccountOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface MemberOption {
  id: string;
  full_name: string;
  member_number: string;
}
export interface ProductOption {
  id: string;
  name: string;
}

export function OpenAccountForm({
  members,
  products,
  defaultMemberId,
}: {
  members: MemberOption[];
  products: ProductOption[];
  defaultMemberId?: string;
}) {
  const router = useRouter();
  const { resources } = useAuth();

  const form = useForm<OpenShareAccountInput>({
    resolver: zodResolver(openShareAccountSchema),
    defaultValues: {
      member_id: defaultMemberId ?? "",
      share_product_id: "",
    },
  });

  const mutation = useTypedMutation<ShareAccountOut, OpenShareAccountInput>(
    async (vars) => {
      const res = await (
        resources.shares.openAccount(vars) as Promise<{
          data?: ShareAccountOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as ShareAccountOut;
    },
    {
      onSuccess: (data) => {
        toast.success("Account opened");
        router.push(`/shares/accounts/${data.id}`);
      },
      onError: (error) => {
        toast.error("The account was not opened", {
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
      <FormField control={form.control} name="member_id" label="Member" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose a member…" />
            </SelectTrigger>
            <SelectContent>
              {members.map((m) => (
                <SelectItem key={m.id} value={m.id}>{m.full_name} ({m.member_number})</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="share_product_id" label="Product" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose a product…" />
            </SelectTrigger>
            <SelectContent>
              {products.map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )} />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Open account</Button>
        <Button type="button" variant="ghost" onClick={() => router.push("/shares/accounts")}>Cancel</Button>
      </div>
    </form>
  );
}
