// admin/apps/portal/app/(tenant-authed)/shares/products/new/_components/CreateProductForm.tsx
"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  FormField,
  Input,
  MoneyInput,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  toast,
} from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import {
  shareProductSchema,
  type ShareProductInput,
  type ShareProductOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface GlAccountOption {
  id: string;
  code: string;
  name: string;
  account_type: string;
}

export function CreateProductForm({ glAccounts }: { glAccounts: GlAccountOption[] }) {
  const router = useRouter();
  const { resources } = useAuth();

  const form = useForm<ShareProductInput>({
    resolver: zodResolver(shareProductSchema),
    defaultValues: {
      name: "",
      par_value: "",
      minimum_shares: "1",
      maximum_shares: "",
      share_capital_account_id: "",
    },
  });

  const mutation = useTypedMutation<ShareProductOut, ShareProductInput>(
    async (vars) => {
      const body: Record<string, unknown> = { ...vars };
      if (!body["maximum_shares"]) delete body["maximum_shares"];
      const res = await (
        resources.shares.createProduct(body) as Promise<{
          data?: ShareProductOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as ShareProductOut;
    },
    {
      onSuccess: () => {
        toast.success("Product created");
        router.push("/shares");
      },
      onError: (error) => {
        toast.error("The product was not created", {
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
      <FormField control={form.control} name="name" label="Name" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="par_value" label="Par value" required
        render={({ field, id, describedBy, invalid }) => (
          <MoneyInput id={id} aria-describedby={describedBy} aria-invalid={invalid}
            value={field.value ?? ""} onValueChange={field.onChange}
            onBlur={field.onBlur} name={field.name} ref={field.ref} />
        )} />
      <FormField control={form.control} name="minimum_shares" label="Minimum shares" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} inputMode="numeric" aria-describedby={describedBy}
            aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="maximum_shares" label="Maximum shares (optional)"
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} inputMode="numeric" aria-describedby={describedBy}
            aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="share_capital_account_id" label="Share capital GL account" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose a GL account…" />
            </SelectTrigger>
            <SelectContent>
              {glAccounts.map((a) => (
                <SelectItem key={a.id} value={a.id}>{a.code} — {a.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )} />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Create product</Button>
        <Button type="button" variant="ghost" onClick={() => router.push("/shares")}>Cancel</Button>
      </div>
    </form>
  );
}
