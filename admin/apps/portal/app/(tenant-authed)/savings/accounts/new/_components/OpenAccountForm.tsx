// admin/apps/portal/app/(tenant-authed)/savings/accounts/new/_components/OpenAccountForm.tsx
"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  FormDialog,
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
  openAccountSchema,
  type OpenAccountInput,
  type SavingsAccountOut,
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

  const form = useForm<OpenAccountInput>({
    resolver: zodResolver(openAccountSchema),
    defaultValues: {
      member_id: defaultMemberId ?? "",
      savings_product_id: "",
    },
  });

  const mutation = useTypedMutation<SavingsAccountOut, OpenAccountInput>(
    async (vars) => {
      const res = await (
        resources.savings.createAccount(vars) as Promise<{
          data?: SavingsAccountOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as SavingsAccountOut;
    },
    {
      onSuccess: (data) => {
        toast.success("Account opened");
        router.push(`/savings/accounts/${data.id}`);
      },
      onError: (error) => {
        toast.error("The account was not opened", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  return (
    <FormDialog
      title="Open savings account"
      description="Open a savings account for a member under a product."
      className="max-w-lg"
      onDismiss={() => router.back()}
      onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
      footer={
        <>
          <Button type="button" variant="ghost" onClick={() => router.back()}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
            Open account
          </Button>
        </>
      }
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
      <FormField control={form.control} name="savings_product_id" label="Product" required
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
    </FormDialog>
  );
}
