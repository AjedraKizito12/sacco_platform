// admin/apps/portal/app/(tenant-authed)/ledger/accounts/new/_components/CreateAccountForm.tsx
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
  Textarea,
  toast,
} from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import { accountSchema, type AccountInput, type AccountOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export interface AccountOption {
  id: string;
  code: string;
  name: string;
}

export function CreateAccountForm({ parents }: { parents: AccountOption[] }) {
  const router = useRouter();
  const { resources } = useAuth();

  const form = useForm<AccountInput>({
    resolver: zodResolver(accountSchema),
    defaultValues: {
      code: "",
      name: "",
      account_type: "asset",
      parent_id: undefined,
      description: "",
    },
  });

  const mutation = useTypedMutation<AccountOut, AccountInput>(
    async (vars) => {
      const body: Record<string, unknown> = { ...vars };
      if (!body["description"]) delete body["description"];
      if (!body["parent_id"] || body["parent_id"] === "none") delete body["parent_id"];
      const res = await (
        resources.ledger.createAccount(body) as Promise<{ data?: AccountOut; error?: unknown }>
      );
      if (res.error) throw res.error;
      return res.data as AccountOut;
    },
    {
      onSuccess: () => {
        toast.success("Account created");
        router.push("/ledger/accounts");
      },
      onError: (error) => {
        toast.error("The account was not created", {
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
      <FormField control={form.control} name="code" label="Code" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="name" label="Name" required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <FormField control={form.control} name="account_type" label="Account type" required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Choose…" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="asset">Asset</SelectItem>
              <SelectItem value="liability">Liability</SelectItem>
              <SelectItem value="equity">Equity</SelectItem>
              <SelectItem value="income">Income</SelectItem>
              <SelectItem value="expense">Expense</SelectItem>
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="parent_id" label="Parent account (optional)"
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value || "none"} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="None" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">None</SelectItem>
              {parents.map((p) => (
                <SelectItem key={p.id} value={p.id}>{p.code} — {p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        )} />
      <FormField control={form.control} name="description" label="Description"
        render={({ field, id, describedBy, invalid }) => (
          <Textarea id={id} rows={2} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )} />
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>Create account</Button>
        <Button type="button" variant="ghost" onClick={() => router.push("/ledger/accounts")}>Cancel</Button>
      </div>
    </form>
  );
}
