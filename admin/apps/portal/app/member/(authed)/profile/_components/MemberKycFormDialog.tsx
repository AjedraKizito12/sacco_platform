"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  DateInput,
  FormDialog,
  FormField,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@sacco/ui";
import {
  ID_DOCUMENT_TYPES,
  MEMBER_KYC_FIELDS,
  memberKycFormDefaults,
  memberKycFormSchema,
  type MemberKycFormInput,
  type MemberKycValues,
} from "@sacco/schemas";

const ID_DOCUMENT_LABELS: Record<(typeof ID_DOCUMENT_TYPES)[number], string> = {
  national_id: "National ID",
  passport: "Passport",
  driving_license: "Driving license",
};

export function MemberKycFormDialog({
  title,
  initialValues,
  busy,
  onDismiss,
  onSubmit,
}: {
  title: string;
  initialValues: MemberKycValues;
  busy: boolean;
  onDismiss: () => void;
  onSubmit: (input: MemberKycFormInput) => void;
}) {
  const form = useForm<MemberKycFormInput>({
    resolver: zodResolver(memberKycFormSchema),
    defaultValues: memberKycFormDefaults(initialValues),
  });

  return (
    <FormDialog
      title={title}
      description="Your details are reviewed by SACCO staff before they are applied."
      onDismiss={onDismiss}
      onSubmit={form.handleSubmit(onSubmit)}
      footer={
        <>
          <Button type="button" variant="secondary" onClick={onDismiss} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" disabled={busy}>
            Submit for review
          </Button>
        </>
      }
    >
      {MEMBER_KYC_FIELDS.map((spec) => (
        <FormField
          key={spec.key}
          control={form.control}
          name={spec.key}
          label={spec.label}
          render={({ field, id, describedBy, invalid }) =>
            spec.kind === "select" ? (
              <Select value={field.value ?? ""} onValueChange={field.onChange}>
                <SelectTrigger id={id} aria-describedby={describedBy} aria-invalid={invalid}>
                  <SelectValue placeholder="Select a document type" />
                </SelectTrigger>
                <SelectContent>
                  {ID_DOCUMENT_TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {ID_DOCUMENT_LABELS[t]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : spec.kind === "date" ? (
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
            ) : (
              <Input
                id={id}
                type={spec.kind === "email" ? "email" : "text"}
                aria-describedby={describedBy}
                aria-invalid={invalid}
                {...field}
              />
            )
          }
        />
      ))}
    </FormDialog>
  );
}
