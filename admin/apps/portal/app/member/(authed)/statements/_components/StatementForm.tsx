"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button, Card, DateInput, FormField } from "@sacco/ui";
import {
  memberStatementRangeSchema,
  type MemberStatementRangeInput,
} from "@sacco/schemas";

function statementUrl(
  values: MemberStatementRangeInput,
  format: "pdf" | "html",
): string {
  const params = new URLSearchParams({ format });
  if (values.from_date) params.set("from_date", values.from_date);
  if (values.to_date) params.set("to_date", values.to_date);
  return `/api/member/statement?${params.toString()}`;
}

export function StatementForm() {
  const form = useForm<MemberStatementRangeInput>({
    resolver: zodResolver(memberStatementRangeSchema),
    defaultValues: { from_date: "", to_date: "" },
  });

  const open = (format: "pdf" | "html") =>
    form.handleSubmit((values) => {
      window.open(statementUrl(values, format), "_blank", "noopener,noreferrer");
    });

  return (
    <Card className="max-w-xl space-y-4 p-6">
      <p className="text-[var(--text-secondary)]">
        Download a consolidated statement of your savings, shares, loans, and
        fees. Leave the dates blank for a full-history statement.
      </p>
      <form className="space-y-4">
        <FormField
          control={form.control}
          name="from_date"
          label="From"
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
          name="to_date"
          label="To"
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
          <Button type="button" onClick={open("pdf")}>
            Download PDF
          </Button>
          <Button type="button" variant="secondary" onClick={open("html")}>
            Preview in browser
          </Button>
        </div>
      </form>
    </Card>
  );
}
