"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Button,
  Checkbox,
  DataTable,
  type DataTableProps,
  FormattedDateTime,
  FormDialog,
  FormField,
  Textarea,
  toast,
  useTableUrlState,
} from "@sacco/ui";
import { queryKeys, useTypedMutation } from "@sacco/api-client";
import {
  notificationTemplatePatchSchema,
  type NotificationTemplateOut,
  type NotificationTemplatePatchInput,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

export function TemplatesTable({ rows }: { rows: NotificationTemplateOut[] }) {
  const [editing, setEditing] = useState<NotificationTemplateOut | null>(null);

  const urlState = useTableUrlState({
    shallow: false,
    defaultSort: { column: "code", direction: "asc" },
    defaultPageSize: 25,
    filterKeys: [],
  });

  const columns: DataTableProps<NotificationTemplateOut>["columns"] = [
    {
      id: "code",
      accessorKey: "code",
      header: "Code",
      cell: ({ row }) => (
        <span className="font-mono text-[12px]">{row.original.code}</span>
      ),
    },
    { id: "channel", accessorKey: "channel", header: "Channel" },
    { id: "locale", accessorKey: "locale", header: "Locale" },
    {
      id: "is_active",
      accessorKey: "is_active",
      header: "Status",
      cell: ({ row }) => (row.original.is_active ? "Active" : "Inactive"),
    },
    {
      id: "updated_at",
      accessorKey: "updated_at",
      header: "Updated",
      cell: ({ row }) => <FormattedDateTime value={row.original.updated_at} />,
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      cell: ({ row }) => (
        <Button variant="ghost" onClick={() => setEditing(row.original)}>
          Edit
        </Button>
      ),
    },
  ];

  return (
    <>
      <DataTable<NotificationTemplateOut>
        id="platform-notification-templates"
        columns={columns}
        data={rows}
        urlState={urlState}
        state={{
          totalRows: rows.length,
          isError: false,
          isPermissionDenied: false,
        }}
        emptyState={{
          title: "No notification templates",
          description:
            "Templates are seeded by migration; new event codes add their templates there.",
        }}
      />
      {editing ? (
        <EditTemplateDialog
          template={editing}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </>
  );
}

function EditTemplateDialog({
  template,
  onClose,
}: {
  template: NotificationTemplateOut;
  onClose: () => void;
}) {
  const router = useRouter();
  const { resources } = useAuth();

  const form = useForm<NotificationTemplatePatchInput>({
    resolver: zodResolver(notificationTemplatePatchSchema),
    defaultValues: {
      subject_template: template.subject_template ?? "",
      body_text: template.body_text ?? "",
      body_html: template.body_html ?? "",
      sms_body: template.sms_body ?? "",
      is_active: template.is_active,
    },
  });

  const mutation = useTypedMutation<unknown, NotificationTemplatePatchInput>(
    async (patch) => {
      const res = await (resources.notifications.patchTemplate(
        template.id,
        patch,
      ) as Promise<{ data?: NotificationTemplateOut; error?: unknown }>);
      if (res.error) throw res.error;
      return res.data;
    },
    {
      invalidates: [queryKeys.notifications.templates()],
      onSuccess: () => {
        toast.success("Template saved");
        onClose();
        router.refresh();
      },
      onError: (error) => {
        toast.error("The template was not saved", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const submit = form.handleSubmit((values) => {
    // PATCH semantics: send only fields the operator actually changed,
    // diffed against the row (null template fields render as "").
    const patch: NotificationTemplatePatchInput = {};
    if (values.subject_template !== (template.subject_template ?? "")) {
      patch.subject_template = values.subject_template ?? "";
    }
    if (values.body_text !== (template.body_text ?? "")) {
      patch.body_text = values.body_text ?? "";
    }
    if (values.body_html !== (template.body_html ?? "")) {
      patch.body_html = values.body_html ?? "";
    }
    if (values.sms_body !== (template.sms_body ?? "")) {
      patch.sms_body = values.sms_body ?? "";
    }
    if (values.is_active !== undefined && values.is_active !== template.is_active) {
      patch.is_active = values.is_active;
    }
    if (Object.keys(patch).length === 0) {
      onClose();
      return;
    }
    mutation.mutate(patch);
  });

  return (
    <FormDialog
      title={`Edit template — ${template.code} (${template.channel})`}
      description="Template variables use {{name}} placeholders from the allow-list."
      onDismiss={onClose}
      onSubmit={submit}
      footer={
        <>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "Saving…" : "Save changes"}
          </Button>
        </>
      }
    >
      <FormField
        control={form.control}
        name="subject_template"
        label="Subject"
        render={({ field, id, describedBy, invalid }) => (
          <Textarea
            {...field}
            id={id}
            rows={1}
            aria-describedby={describedBy}
            aria-invalid={invalid}
          />
        )}
      />
      <FormField
        control={form.control}
        name="body_text"
        label="Body (plain text)"
        render={({ field, id, describedBy, invalid }) => (
          <Textarea
            {...field}
            id={id}
            rows={5}
            aria-describedby={describedBy}
            aria-invalid={invalid}
          />
        )}
      />
      <FormField
        control={form.control}
        name="body_html"
        label="Body (HTML)"
        render={({ field, id, describedBy, invalid }) => (
          <Textarea
            {...field}
            id={id}
            rows={5}
            aria-describedby={describedBy}
            aria-invalid={invalid}
          />
        )}
      />
      <FormField
        control={form.control}
        name="sms_body"
        label="SMS body"
        render={({ field, id, describedBy, invalid }) => (
          <Textarea
            {...field}
            id={id}
            rows={2}
            aria-describedby={describedBy}
            aria-invalid={invalid}
          />
        )}
      />
      <FormField
        control={form.control}
        name="is_active"
        label="Active"
        render={({ field, id, describedBy }) => (
          <Checkbox
            id={id}
            aria-describedby={describedBy}
            checked={field.value === true}
            onCheckedChange={(checked) => field.onChange(checked === true)}
          />
        )}
      />
    </FormDialog>
  );
}
