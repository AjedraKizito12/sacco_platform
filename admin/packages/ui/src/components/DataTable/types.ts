import type { ColumnDef } from "@tanstack/react-table";
import type { ReactNode } from "react";

export type Density = "default" | "compact";
export type SortDirection = "asc" | "desc";

export interface TableUrlState {
  page: number; // 1-indexed
  pageSize: number;
  sortColumn: string | null;
  sortDirection: SortDirection;
  filters: Record<string, string>;
  density: Density;
  setPage(page: number): void;
  setPageSize(size: number): void;
  setSort(column: string | null, direction: SortDirection): void;
  setFilter(key: string, value: string | null): void;
  setFilters(values: Record<string, string | null>): void;
  setDensity(d: Density): void;
  reset(): void;
}

export interface DataTableServerState {
  totalRows: number;
  isError: boolean;
  isPermissionDenied: boolean;
  error?: { message: string; requestId?: string | null };
}

export interface BulkActionContext {
  /** IDs of the rows currently selected on the page. */
  selectedIds: string[];
  /** True when the user clicked "Select all N matching" — the consumer
   *  should apply the action to all matching rows on the server. */
  selectedAllMatching: boolean;
}

export interface BulkActions<TData> {
  /** Called when the operator confirms a bulk action against the page selection. */
  onActionOnPage(ctx: BulkActionContext, action: string): void | Promise<void>;
  /** Called when the operator confirms a bulk action against all matching rows. */
  onActionOnAllMatching?(
    ctx: BulkActionContext,
    action: string,
  ): void | Promise<void>;
  /** Available actions. Keyed by `action` string passed back through the callbacks. */
  actions: Array<{ id: string; label: string; destructive?: boolean }>;
  /** Carrier type only — TanStack's row generic. */
  _typeBrand?: TData;
}

export interface DataTableEmptyState {
  title: string;
  description?: string;
  action?: ReactNode;
}

export interface DataTableProps<TData extends { id: string }> {
  /** Stable identifier for cookie-backed preferences. */
  id: string;
  columns: ColumnDef<TData>[];
  /** undefined → loading. */
  data: TData[] | undefined;
  state: DataTableServerState;
  urlState: TableUrlState;
  emptyState: DataTableEmptyState;
  bulk?: BulkActions<TData>;
  /** Slot for filter inputs above the toolbar. */
  filterSlot?: ReactNode;
  /** When false, the CSV export button is hidden. */
  exportEnabled?: boolean;
}
