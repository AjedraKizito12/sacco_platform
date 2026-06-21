// admin/apps/portal/app/(tenant-authed)/reports/fee-collection/_components/FeeCollectionTable.tsx
"use client";

import { useMemo } from "react";
import {
  DataTable,
  type DataTableProps,
  Money,
  useTableUrlState,
} from "@sacco/ui";
import type { FeeCollectionRowOut } from "@sacco/schemas";

type Row = FeeCollectionRowOut & { id: string };

const columns: DataTableProps<Row>["columns"] = [
  { id: "fee_type_name", accessorKey: "fee_type_name", header: "Fee type" },
  { id: "target_type", accessorKey: "target_type", header: "Target" },
  {
    id: "assessed_total",
    accessorKey: "assessed_total",
    header: "Assessed",
    cell: ({ row }) => <Money amount={row.original.assessed_total} />,
  },
  {
    id: "collected_total",
    accessorKey: "collected_total",
    header: "Collected",
    cell: ({ row }) => <Money amount={row.original.collected_total} />,
  },
  {
    id: "outstanding_total",
    accessorKey: "outstanding_total",
    header: "Outstanding",
    cell: ({ row }) => <Money amount={row.original.outstanding_total} />,
  },
  {
    id: "waived_total",
    accessorKey: "waived_total",
    header: "Waived",
    cell: ({ row }) => <Money amount={row.original.waived_total} />,
  },
];

export function FeeCollectionTable({ rows }: { rows: FeeCollectionRowOut[] }) {
  const urlState = useTableUrlState({ defaultPageSize: 100 });
  const withIds = useMemo<Row[]>(() => rows.map((r, i) => ({ ...r, id: String(i) })), [rows]);
  const pageRows = useMemo(() => {
    const start = (urlState.page - 1) * urlState.pageSize;
    return withIds.slice(start, start + urlState.pageSize);
  }, [withIds, urlState.page, urlState.pageSize]);

  return (
    <DataTable<Row>
      id="fee-collection"
      columns={columns}
      data={pageRows}
      urlState={urlState}
      state={{ totalRows: rows.length, isError: false, isPermissionDenied: false }}
      emptyState={{
        title: "No fee-collection data",
        description: "Choose a period to view.",
      }}
    />
  );
}
