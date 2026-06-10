"use client";

import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
  type RowSelectionState,
  type VisibilityState,
} from "@tanstack/react-table";
import {
  type CSSProperties,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { cn } from "../../utils/cn";
import { Checkbox } from "../Checkbox";
import { BulkBanner } from "./BulkBanner";
import { Pagination } from "./Pagination";
import { Toolbar, type ToolbarColumn } from "./Toolbar";
import { downloadCsv, rowsToCsv } from "./csv";
import { EmptyState } from "./states/EmptyState";
import { ErrorState } from "./states/ErrorState";
import { FilterEmptyState } from "./states/FilterEmptyState";
import { PermissionDeniedState } from "./states/PermissionDeniedState";
import { SkeletonRows } from "./states/SkeletonRows";
import {
  getTablePrefs,
  setTableDensity,
  setTableHiddenColumns,
} from "./table-prefs";
import type { DataTableProps } from "./types";

const SELECTION_COL_ID = "__select";

export function DataTable<TData extends { id: string }>({
  id,
  columns: userColumns,
  data,
  state,
  urlState,
  emptyState,
  bulk,
  filterSlot,
  exportEnabled = true,
}: DataTableProps<TData>) {
  // Augment columns with a selection column when bulk is enabled.
  const columns = useMemo<ColumnDef<TData>[]>(() => {
    if (!bulk) return userColumns;
    const selectionCol: ColumnDef<TData> = {
      id: SELECTION_COL_ID,
      header: ({ table }) => (
        <Checkbox
          checked={
            table.getIsAllPageRowsSelected()
              ? true
              : table.getIsSomePageRowsSelected()
                ? "indeterminate"
                : false
          }
          onCheckedChange={(v) => table.toggleAllPageRowsSelected(Boolean(v))}
          aria-label="Select all rows on this page"
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(v) => row.toggleSelected(Boolean(v))}
          aria-label="Select row"
        />
      ),
      size: 36,
      enableSorting: false,
    };
    return [selectionCol, ...userColumns];
  }, [bulk, userColumns]);

  // Column visibility — initialize from cookie.
  const initialPrefs = useMemo(() => getTablePrefs(id), [id]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(
    () =>
      Object.fromEntries(initialPrefs.hiddenColumns.map((c) => [c, false])),
  );

  useEffect(() => {
    const hidden = Object.entries(columnVisibility)
      .filter(([, v]) => !v)
      .map(([k]) => k);
    setTableHiddenColumns(id, hidden);
  }, [columnVisibility, id]);

  useEffect(() => {
    setTableDensity(id, urlState.density);
  }, [id, urlState.density]);

  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [allMatchingSelected, setAllMatchingSelected] = useState(false);

  const table = useReactTable<TData>({
    data: data ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    manualFiltering: true,
    state: { rowSelection, columnVisibility },
    onRowSelectionChange: (updater) => {
      setRowSelection(updater);
      setAllMatchingSelected(false);
    },
    onColumnVisibilityChange: setColumnVisibility,
    getRowId: (row) => row.id,
  });

  // Sort header behaviour — clicking toggles asc → desc → off.
  const onSortClick = useCallback(
    (columnId: string) => {
      if (urlState.sortColumn === columnId) {
        urlState.setSort(
          urlState.sortDirection === "asc" ? columnId : null,
          urlState.sortDirection === "asc" ? "desc" : "asc",
        );
      } else {
        urlState.setSort(columnId, "asc");
      }
    },
    [urlState],
  );

  // Toolbar config.
  const toolbarColumns = useMemo<ToolbarColumn[]>(
    () =>
      userColumns
        .filter((c): c is ColumnDef<TData> & { id: string } => Boolean(c.id))
        .map((c) => ({
          id: c.id,
          header: typeof c.header === "string" ? c.header : c.id,
        })),
    [userColumns],
  );
  const hiddenColumnIds = Object.entries(columnVisibility)
    .filter(([, v]) => !v)
    .map(([k]) => k);

  const onToggleColumn = useCallback(
    (colId: string) =>
      setColumnVisibility((prev) => ({
        ...prev,
        [colId]: prev[colId] === false ? true : false,
      })),
    [],
  );

  // CSV export — uses currently-visible columns + currently-loaded rows.
  const onExportCsv = useCallback(() => {
    const rows = (data ?? []).map(
      (r) => r as unknown as Record<string, unknown>,
    );
    const cols = userColumns
      .filter(
        (c): c is ColumnDef<TData> & { id: string } =>
          Boolean(c.id) && !hiddenColumnIds.includes(c.id as string),
      )
      .map((c) => ({
        key: c.id,
        header: typeof c.header === "string" ? c.header : c.id,
      }));
    downloadCsv(`${id}.csv`, rowsToCsv(rows, cols));
  }, [data, hiddenColumnIds, id, userColumns]);

  // Bulk.
  const selectedIds = Object.keys(rowSelection).filter(
    (rowId) => rowSelection[rowId],
  );
  const onActionClick = useCallback(
    (actionId: string) => {
      if (!bulk) return;
      if (allMatchingSelected && bulk.onActionOnAllMatching) {
        void bulk.onActionOnAllMatching(
          { selectedIds, selectedAllMatching: true },
          actionId,
        );
      } else {
        void bulk.onActionOnPage(
          { selectedIds, selectedAllMatching: false },
          actionId,
        );
      }
    },
    [allMatchingSelected, bulk, selectedIds],
  );

  const isLoading = data === undefined;
  const isPermDenied = state.isPermissionDenied;
  const isError = state.isError;
  const hasFilters = Object.keys(urlState.filters).length > 0;
  const isEmpty =
    !isLoading && !isError && !isPermDenied && (data ?? []).length === 0;
  const showFilterEmpty = isEmpty && hasFilters;
  const showEmpty = isEmpty && !hasFilters;

  const rowHeightVar: CSSProperties =
    urlState.density === "compact"
      ? { ["--row-h" as never]: "var(--height-table-row-compact)" }
      : { ["--row-h" as never]: "var(--height-table-row)" };

  return (
    <div className="overflow-hidden rounded-[var(--radius-card)] border border-[var(--border-subtle)] bg-[var(--surface-elevated)]">
      <Toolbar
        filterSlot={filterSlot}
        density={urlState.density}
        onDensityChange={urlState.setDensity}
        columns={toolbarColumns}
        hiddenColumnIds={hiddenColumnIds}
        onToggleColumn={onToggleColumn}
        {...(exportEnabled ? { onExportCsv } : {})}
      />
      {bulk && selectedIds.length > 0 ? (
        <BulkBanner
          selectedOnPage={selectedIds.length}
          totalMatching={state.totalRows}
          pageSize={urlState.pageSize}
          allMatchingSelected={allMatchingSelected}
          onSelectAllMatching={() => setAllMatchingSelected(true)}
          onClearSelection={() => {
            setRowSelection({});
            setAllMatchingSelected(false);
          }}
          actions={bulk.actions}
          onActionClick={onActionClick}
        />
      ) : null}
      {isPermDenied ? (
        <PermissionDeniedState />
      ) : isError ? (
        <ErrorState
          message={state.error?.message ?? "An unexpected error occurred."}
          {...(state.error?.requestId !== undefined
            ? { requestId: state.error.requestId }
            : {})}
        />
      ) : showEmpty ? (
        <EmptyState
          title={emptyState.title}
          {...(emptyState.description !== undefined
            ? { description: emptyState.description }
            : {})}
          {...(emptyState.action !== undefined
            ? { action: emptyState.action }
            : {})}
        />
      ) : showFilterEmpty ? (
        <FilterEmptyState onClearFilter={urlState.reset} />
      ) : (
        <div className="overflow-x-auto" style={rowHeightVar}>
          <table className="w-full border-collapse text-[14px]">
            <thead className="sticky top-0 z-[1] bg-[var(--surface-sunken)]">
              {table.getHeaderGroups().map((group) => (
                <tr
                  key={group.id}
                  className="h-[var(--height-table-header)] text-[12px] uppercase tracking-wider text-[var(--text-tertiary)]"
                >
                  {group.headers.map((header) => {
                    const canSort =
                      header.column.id !== SELECTION_COL_ID &&
                      (header.column.columnDef.enableSorting ?? true);
                    const isSorted = urlState.sortColumn === header.column.id;
                    return (
                      <th
                        key={header.id}
                        scope="col"
                        className={cn(
                          "px-4 text-left font-medium",
                          canSort && "cursor-pointer select-none",
                          isSorted && "text-[var(--text-primary)]",
                        )}
                        onClick={
                          canSort
                            ? () => onSortClick(header.column.id)
                            : undefined
                        }
                      >
                        {flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                        {isSorted
                          ? urlState.sortDirection === "asc"
                            ? " ▲"
                            : " ▼"
                          : null}
                      </th>
                    );
                  })}
                </tr>
              ))}
            </thead>
            <tbody>
              {isLoading ? (
                <SkeletonRows
                  columnCount={columns.length}
                  density={urlState.density}
                />
              ) : (
                table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    className={cn(
                      "h-[var(--row-h)] border-b border-[var(--border-subtle)]",
                      "hover:bg-[var(--surface-hover)]",
                      row.getIsSelected() && "bg-[var(--surface-selected)]",
                    )}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-4">
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
      {!isError && !isPermDenied && !isEmpty ? (
        <Pagination
          page={urlState.page}
          pageSize={urlState.pageSize}
          totalRows={state.totalRows}
          onPageChange={urlState.setPage}
          onPageSizeChange={urlState.setPageSize}
        />
      ) : null}
    </div>
  );
}
