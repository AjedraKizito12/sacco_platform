"use client";

import { useState } from "react";
import {
  Button,
  DataTable,
  type DataTableProps,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  FormattedDateTime,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  useTableUrlState,
} from "@sacco/ui";
import { AUDIT_OPERATION_OPTIONS, type AuditEntryOut } from "@sacco/schemas";
import { AuditOperationLabel } from "./AuditOperationLabel";
import { JsonDiff } from "./JsonDiff";

function actorOf(e: AuditEntryOut): string {
  return e.actor_label ?? e.actor_id ?? e.actor_type;
}

export function AuditTable({
  items,
  total,
  showImpersonation,
}: {
  items: AuditEntryOut[];
  total: number;
  showImpersonation: boolean;
}) {
  const [openRow, setOpenRow] = useState<AuditEntryOut | null>(null);

  const urlState = useTableUrlState({
    shallow: false,
    defaultSort: { column: "occurred_at", direction: "desc" },
    defaultPageSize: 25,
    filterKeys: [
      "table_name",
      "operation",
      "actor_id",
      "record_id",
      "occurred_from",
      "occurred_to",
    ],
  });

  const columns: DataTableProps<AuditEntryOut>["columns"] = [
    {
      id: "occurred_at",
      accessorKey: "occurred_at",
      header: "When",
      cell: ({ row }) => <FormattedDateTime value={row.original.occurred_at} />,
    },
    { id: "table_name", accessorKey: "table_name", header: "Table" },
    {
      id: "record_id",
      accessorKey: "record_id",
      header: "Record",
      cell: ({ row }) => (
        <span className="font-mono text-[12px]">{row.original.record_id}</span>
      ),
    },
    {
      id: "operation",
      accessorKey: "operation",
      header: "Operation",
      cell: ({ row }) => <AuditOperationLabel operation={row.original.operation} />,
    },
    {
      id: "actor",
      accessorKey: "actor_label",
      header: "Actor",
      enableSorting: false,
      cell: ({ row }) => actorOf(row.original),
    },
    ...(showImpersonation
      ? [
          {
            id: "impersonation_id",
            accessorKey: "impersonation_id",
            header: "Impersonation",
            enableSorting: false,
            cell: ({ row }: { row: { original: AuditEntryOut } }) =>
              row.original.impersonation_id ? (
                <span className="font-mono text-[12px]">{row.original.impersonation_id}</span>
              ) : (
                <span className="text-[var(--text-tertiary)]">—</span>
              ),
          },
        ]
      : []),
    {
      id: "details",
      header: "",
      enableSorting: false,
      cell: ({ row }) => (
        <Button variant="ghost" onClick={() => setOpenRow(row.original)}>
          Details
        </Button>
      ),
    },
  ];

  return (
    <>
      <DataTable<AuditEntryOut>
        id="platform-audit"
        columns={columns}
        data={items}
        urlState={urlState}
        state={{ totalRows: total, isError: false, isPermissionDenied: false }}
        emptyState={{
          title: "No audit entries",
          description: "Audit entries appear as operators and the system act on records.",
        }}
        filterSlot={
          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={urlState.filters["operation"] ?? "all"}
              onValueChange={(v) =>
                urlState.setFilter("operation", v === "all" ? null : v)
              }
            >
              <SelectTrigger className="w-40" aria-label="Filter by operation">
                <SelectValue placeholder="All operations" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All operations</SelectItem>
                {AUDIT_OPERATION_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              className="w-40"
              placeholder="Table"
              aria-label="Filter by table"
              defaultValue={urlState.filters["table_name"] ?? ""}
              onBlur={(e) => urlState.setFilter("table_name", e.target.value || null)}
            />
            <Input
              className="w-64"
              placeholder="Record ID"
              aria-label="Filter by record id"
              defaultValue={urlState.filters["record_id"] ?? ""}
              onBlur={(e) => urlState.setFilter("record_id", e.target.value || null)}
            />
            <Input
              className="w-64"
              placeholder="Actor ID"
              aria-label="Filter by actor id"
              defaultValue={urlState.filters["actor_id"] ?? ""}
              onBlur={(e) => urlState.setFilter("actor_id", e.target.value || null)}
            />
          </div>
        }
      />

      <Dialog open={openRow !== null} onOpenChange={(o) => { if (!o) setOpenRow(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {openRow ? `${openRow.operation} · ${openRow.table_name}` : "Audit entry"}
            </DialogTitle>
          </DialogHeader>
          {openRow ? (
            <JsonDiff before={openRow.before_state} after={openRow.after_state} />
          ) : null}
        </DialogContent>
      </Dialog>
    </>
  );
}
