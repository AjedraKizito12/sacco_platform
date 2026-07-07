// admin/apps/portal/app/(tenant-authed)/ledger/journal-entries/_components/JournalEntriesTable.tsx
"use client";

import { useMemo } from "react";
import Link from "next/link";
import { Count, DataTable, type DataTableProps, FormattedDateTime, useTableUrlState } from "@sacco/ui";
import type { JournalEntryOut } from "@sacco/schemas";

const columns: DataTableProps<JournalEntryOut>["columns"] = [
  {
    id: "reference",
    accessorKey: "reference",
    header: "Reference",
    cell: ({ row }) => (
      <Link
        href={`/ledger/journal-entries/${row.original.id}`}
        className="font-medium text-[var(--text-link)]"
      >
        {row.original.reference}
      </Link>
    ),
  },
  { id: "description", accessorKey: "description", header: "Description" },
  {
    id: "posted_at",
    accessorKey: "posted_at",
    header: "Posted",
    cell: ({ row }) => <FormattedDateTime value={row.original.posted_at} />,
  },
  {
    id: "lines",
    header: "Lines",
    cell: ({ row }) => <Count value={row.original.lines.length} />,
  },
];

function sortRows(
  rows: JournalEntryOut[],
  column: string | null,
  dir: "asc" | "desc",
): JournalEntryOut[] {
  if (!column) return rows;
  const sorted = [...rows].sort((a, b) => {
    const av = a[column as keyof JournalEntryOut];
    const bv = b[column as keyof JournalEntryOut];
    return String(av ?? "").localeCompare(String(bv ?? ""));
  });
  return dir === "desc" ? sorted.reverse() : sorted;
}

export function JournalEntriesTable({ rows }: { rows: JournalEntryOut[] }) {
  const urlState = useTableUrlState({
    defaultSort: { column: "posted_at", direction: "desc" },
    defaultPageSize: 50,
  });
  const sorted = useMemo(
    () => sortRows(rows, urlState.sortColumn, urlState.sortDirection),
    [rows, urlState.sortColumn, urlState.sortDirection],
  );
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return sorted.slice(start, start + urlState.pageSize);
  }, [sorted, urlState.page, urlState.pageSize]);

  return (
    <DataTable<JournalEntryOut>
      id="ledger-journal"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No journal entries yet",
        description: "Post a manual GL entry to get started.",
      }}
    />
  );
}
