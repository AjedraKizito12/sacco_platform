"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Button,
  ConfirmDialog,
  DataTable,
  type DataTableProps,
  FormattedDateTime,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusBadge,
  toast,
  useTableUrlState,
} from "@sacco/ui";
import { useTypedMutation } from "@sacco/api-client";
import {
  PORTAL_NOTIFICATION_CATALOG,
  type NotificationEventAdminOut,
} from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";
import { apiErrorMessage } from "@/lib/api-error";

const EVENT_STATUSES = ["queued", "sent", "partial", "failed", "cancelled"];

export function EventsTable({
  rows,
  totalRows,
}: {
  rows: NotificationEventAdminOut[];
  totalRows: number;
}) {
  const router = useRouter();
  const { resources } = useAuth();
  const [resending, setResending] = useState<NotificationEventAdminOut | null>(
    null,
  );

  const urlState = useTableUrlState({
    shallow: false,
    defaultSort: { column: "created_at", direction: "desc" },
    defaultPageSize: 25,
    filterKeys: ["status", "event_code"],
  });

  const mutation = useTypedMutation<unknown, string>(
    async (eventId) => {
      const res = await (resources.notifications.resendEvent(
        eventId,
      ) as Promise<{ data?: NotificationEventAdminOut; error?: unknown }>);
      if (res.error) throw res.error;
      return res.data;
    },
    {
      onSuccess: () => {
        toast.success("Notification re-queued for delivery");
        setResending(null);
        router.refresh();
      },
      onError: (error) => {
        toast.error("The notification was not re-queued", {
          description: apiErrorMessage(error, "Please try again."),
        });
      },
    },
  );

  const columns: DataTableProps<NotificationEventAdminOut>["columns"] = [
    {
      id: "created_at",
      accessorKey: "created_at",
      header: "Created",
      cell: ({ row }) => <FormattedDateTime value={row.original.created_at} />,
    },
    {
      id: "event_code",
      accessorKey: "event_code",
      header: "Event",
      cell: ({ row }) => (
        <span className="font-mono text-[12px]">{row.original.event_code}</span>
      ),
    },
    {
      id: "recipient",
      accessorKey: "recipient_email",
      header: "Recipient",
      enableSorting: false,
      cell: ({ row }) => (
        <span>
          {row.original.recipient_kind}
          {row.original.recipient_email ? (
            <span className="text-[var(--text-secondary)]">
              {" "}
              · {row.original.recipient_email}
            </span>
          ) : null}
        </span>
      ),
    },
    {
      id: "channels",
      accessorKey: "channels",
      header: "Channels",
      enableSorting: false,
      cell: ({ row }) => row.original.channels.join(", "),
    },
    {
      id: "status",
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => (
        <StatusBadge entity="notification_event" status={row.original.status} />
      ),
    },
    {
      id: "actions",
      header: "",
      enableSorting: false,
      cell: ({ row }) => (
        <Button
          variant="ghost"
          disabled={row.original.status === "queued"}
          onClick={() => setResending(row.original)}
        >
          Resend
        </Button>
      ),
    },
  ];

  return (
    <>
      <DataTable<NotificationEventAdminOut>
        id="platform-notification-events"
        columns={columns}
        data={rows}
        urlState={urlState}
        state={{ totalRows, isError: false, isPermissionDenied: false }}
        emptyState={{
          title: "No notification events",
          description:
            "Platform-scoped notification events appear here as they are published.",
        }}
        filterSlot={
          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={urlState.filters["status"] ?? "all"}
              onValueChange={(v) =>
                urlState.setFilter("status", v === "all" ? null : v)
              }
            >
              <SelectTrigger className="w-40" aria-label="Filter by status">
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {EVENT_STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={urlState.filters["event_code"] ?? "all"}
              onValueChange={(v) =>
                urlState.setFilter("event_code", v === "all" ? null : v)
              }
            >
              <SelectTrigger className="w-64" aria-label="Filter by event code">
                <SelectValue placeholder="All event codes" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All event codes</SelectItem>
                {PORTAL_NOTIFICATION_CATALOG.map((row) => (
                  <SelectItem key={row.code} value={row.code}>
                    {row.code}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        }
      />
      <ConfirmDialog
        open={resending !== null}
        onOpenChange={(open) => {
          if (!open) setResending(null);
        }}
        title="Resend notification?"
        description={
          resending
            ? `Re-queue "${resending.event_code}" for delivery. Channels already delivered are skipped.`
            : undefined
        }
        confirmLabel="Resend notification"
        busy={mutation.isPending}
        onConfirm={() => {
          if (resending) mutation.mutate(resending.id);
        }}
      />
    </>
  );
}
