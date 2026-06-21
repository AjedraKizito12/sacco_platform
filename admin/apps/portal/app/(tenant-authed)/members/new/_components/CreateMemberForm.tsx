// admin/apps/portal/app/(tenant-authed)/members/new/_components/CreateMemberForm.tsx
"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  DateInput,
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
import {
  memberRegistrationSchema,
  type MemberOut,
  type MemberRegistrationInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

const GENDER_OPTIONS = [
  { value: "M", label: "Male" },
  { value: "F", label: "Female" },
  { value: "X", label: "Other" },
] as const;

const ID_DOCUMENT_OPTIONS = [
  { value: "national_id", label: "National ID" },
  { value: "passport", label: "Passport" },
  { value: "driving_license", label: "Driving license" },
  { value: "voters_card", label: "Voter's card" },
] as const;

export function CreateMemberForm() {
  const router = useRouter();
  const { resources } = useAuth();

  const form = useForm<MemberRegistrationInput>({
    resolver: zodResolver(memberRegistrationSchema),
    defaultValues: {
      full_name: "",
      date_of_birth: "",
      phone: "",
      email: "",
      physical_address: "",
      national_id_number: "",
      id_document_number: "",
    },
  });

  const mutation = useTypedMutation<MemberOut, MemberRegistrationInput>(
    async (vars) => {
      const res = await (
        resources.members.create(vars) as Promise<{
          data?: MemberOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      return res.data as MemberOut;
    },
    {
      onSuccess: (data) => {
        toast.success("Member registered");
        router.push(`/members/${data.id}`);
      },
      onError: (error) => {
        toast.error("The member was not registered", {
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
        name="full_name"
        label="Full name"
        required
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )}
      />
      <FormField
        control={form.control}
        name="date_of_birth"
        label="Date of birth"
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
      <FormField
        control={form.control}
        name="gender"
        label="Gender"
        required
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value ?? ""} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Select gender…" />
            </SelectTrigger>
            <SelectContent>
              {GENDER_OPTIONS.map((o) => (
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
        name="phone"
        label="Phone"
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} type="tel" aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )}
      />
      <FormField
        control={form.control}
        name="email"
        label="Email"
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} type="email" aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )}
      />
      <FormField
        control={form.control}
        name="physical_address"
        label="Physical address"
        render={({ field, id, describedBy, invalid }) => (
          <Textarea id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )}
      />
      <FormField
        control={form.control}
        name="national_id_number"
        label="National ID number"
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )}
      />
      <FormField
        control={form.control}
        name="id_document_type"
        label="ID document type"
        render={({ field, id, describedBy, invalid }) => (
          <Select value={field.value ?? ""} onValueChange={field.onChange}>
            <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
              <SelectValue placeholder="Select document type…" />
            </SelectTrigger>
            <SelectContent>
              {ID_DOCUMENT_OPTIONS.map((o) => (
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
        name="id_document_number"
        label="ID document number"
        render={({ field, id, describedBy, invalid }) => (
          <Input id={id} aria-describedby={describedBy} aria-invalid={invalid} {...field} />
        )}
      />
      <FormField
        control={form.control}
        name="id_issued_date"
        label="ID issued date"
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
      <FormField
        control={form.control}
        name="id_expiry_date"
        label="ID expiry date"
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
      <div className="flex gap-3">
        <Button type="submit" disabled={mutation.isPending}>
          Register member
        </Button>
        <Button type="button" variant="ghost" onClick={() => router.push("/members")}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
