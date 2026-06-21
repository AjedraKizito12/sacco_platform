// admin/apps/portal/app/(tenant-authed)/fees/assessments/[id]/_components/CollectionsTable.tsx
"use client";

import { useMemo } from "react";
import {
  DataTable,
  type DataTableProps,
  FormattedDateTime,
  Money,
  useTableUrlState,
} from "@sacco/ui";
import type { FeeCollectionOut } from "@sacco/schemas";

const columns: DataTableProps<FeeCollectionOut>["columns"] = [
  {
    id: "amount",
    accessorKey: "amount",
    header: "Amount",
    cell: ({ row }) => <Money amount={row.original.amount} />,
  },
  { id: "method", accessorKey: "method", header: "Method" },
  {
    id: "collected_at",
    accessorKey: "collected_at",
    header: "Collected",
    cell: ({ row }) => <FormattedDateTime value={row.original.collected_at} />,
  },
];

export function CollectionsTable({ rows }: { rows: FeeCollectionOut[] }) {
  const urlState = useTableUrlState({ defaultPageSize: 25 });
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return rows.slice(start, start + urlState.pageSize);
  }, [rows, urlState.page, urlState.pageSize]);

  return (
    <DataTable<FeeCollectionOut>
      id="fee-collections"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No collections yet",
        description: "Recorded collections appear here.",
      }}
    />
  );
}
