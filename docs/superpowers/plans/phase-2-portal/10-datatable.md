# Portal v1 Sub-Plan 10: DataTable Wrapper

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/portal-v1/10-datatable` from `main` (or rebase on top of sub-plans 01-09).

**Goal:** Ship a single `<DataTable>` component that every list screen in the portal uses. After this sub-plan merges, no feature module rolls its own table. Server-side pagination, sort, and filter. URL-synced state via nuqs so the operator can share a filtered link. Density toggle and column visibility persisted per user via cookies. Five visual states (data / loading / empty / filter-empty / error / permission-denied). Bulk selection with both page-only and "select all matching" affordances. Client-side CSV export from the loaded page.

**Architecture:**
- **TanStack Table v8 is the engine.** We use `useReactTable` in **server-side mode** — `manualPagination`, `manualSorting`, `manualFiltering`. The caller owns data fetching; the table owns rendering, column models, and selection state.
- **State container is `TableUrlState`.** A custom hook (`useTableUrlState`) reads and writes `page`, `sort`, `filter`, and `density` to the URL via `nuqs`'s `useQueryStates`. Sub-plan 11's forms hook into the same `filter` slot. The hook returns plain values + a setter; consumers don't think about the URL.
- **Persistent preferences (column visibility + density default) live in cookies** under `sacco_table_prefs`. The cookie is JSON-encoded `Record<tableId, { hiddenColumns: string[]; density: "default" | "compact" }>`. Each table has a stable `id` prop; preferences are per-table per-user.
- **The component is a presentational shell.** It takes:
  - `columns: ColumnDef<TData>[]`
  - `data: TData[] | undefined` (undefined → loading)
  - `state: { totalRows, isError, isPermissionDenied, error }`
  - `urlState` (from `useTableUrlState`)
  - `bulk?: { onActionOnPage, onActionOnAllMatching }`
  - `emptyState: { title, description, action? }`
- **Five states are exhaustive.** Loading → skeleton rows (never spinner per design system §"Loading States"). Empty data + no filter → `emptyState` prop. Empty data + has filter → "No results match your filter — Clear filter" affordance. Error → inline panel with `request_id` (from `ServerError`) for log correlation. Permission denied → reuses the design system's "permission denied" affordance from sub-plan 08, scoped to the table area.
- **Bulk selection is two-tier.** The checkbox column has a header checkbox selecting the current page. A separate "Select all 1,234 matching" banner appears once the page is fully selected, exposing the `onActionOnAllMatching` callback. The DataTable does not know what "matching" means at the server — the consumer handles it.
- **CSV export is client-side.** A button in the toolbar serializes the current `data` (only the loaded page) to CSV via a small helper. Server-rendered CSV remains a reporting endpoint (sub-plan 29).
- **Sticky header on scroll, sticky first column** are CSS-driven. No JS scroll listeners.

**Tech Stack:** TanStack Table v8, nuqs 2, React 19, `@sacco/ui` primitives (Button, Checkbox, DropdownMenu, etc.).

**Portal v1 index reference:** `docs/superpowers/plans/2026-06-02-portal-v1-index.md` §Sub-plan 10.

**Required reading:**
- `docs/sacco-design-system-v2.md` §"Data Tables", §"Loading States", §"Empty States", §"Permissions UX"
- TanStack Table v8 docs (server-side / "manual" mode)
- nuqs docs (`useQueryStates`)
- Sub-plan 08's `PermissionDeniedError` + AppErrorBoundary

**Prerequisite:** **Sub-plans 04 and 09 must be merged.** Sub-plan 04's `@sacco/ui` primitives (Checkbox, DropdownMenu, Button, Tooltip) and sub-plan 09's display primitives are direct dependencies.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `admin/packages/ui/package.json` | Modify | Add `@tanstack/react-table` + `nuqs` |
| `admin/packages/ui/src/components/DataTable/types.ts` | Create | Public types (`DataTableProps`, `TableUrlState`, `BulkActions`, etc.) |
| `admin/packages/ui/src/components/DataTable/use-table-url-state.ts` | Create | URL-synced state hook via nuqs |
| `admin/packages/ui/src/components/DataTable/table-prefs.ts` | Create | Cookie helpers for column visibility + density |
| `admin/packages/ui/src/components/DataTable/csv.ts` | Create | Client-side CSV serializer |
| `admin/packages/ui/src/components/DataTable/DataTable.tsx` | Create | The component itself |
| `admin/packages/ui/src/components/DataTable/states/SkeletonRows.tsx` | Create | Loading state |
| `admin/packages/ui/src/components/DataTable/states/EmptyState.tsx` | Create | Empty data state |
| `admin/packages/ui/src/components/DataTable/states/FilterEmptyState.tsx` | Create | Empty-with-filter state |
| `admin/packages/ui/src/components/DataTable/states/ErrorState.tsx` | Create | Error state with `request_id` |
| `admin/packages/ui/src/components/DataTable/states/PermissionDeniedState.tsx` | Create | Permission-denied state |
| `admin/packages/ui/src/components/DataTable/Toolbar.tsx` | Create | Filter slot + density toggle + column visibility + CSV export |
| `admin/packages/ui/src/components/DataTable/BulkBanner.tsx` | Create | "X selected · Select all N matching" banner |
| `admin/packages/ui/src/components/DataTable/Pagination.tsx` | Create | Page size + page navigation |
| `admin/packages/ui/src/components/DataTable/index.ts` | Create | Re-exports |
| `admin/packages/ui/src/components/DataTable/*.test.tsx` | Create | Vitest coverage |
| `admin/packages/ui/src/components/DataTable/*.stories.tsx` | Create | Storybook stories |
| `admin/packages/ui/src/index.ts` | Modify | Re-export DataTable |
| `CLAUDE.md` | Modify | Append contract T (every list screen uses DataTable) |

---

## Task 1: Deps + URL state hook + preference cookies

**Files:**
- Modify: `admin/packages/ui/package.json`
- Create: `admin/packages/ui/src/components/DataTable/types.ts`
- Create: `admin/packages/ui/src/components/DataTable/use-table-url-state.ts`
- Create: `admin/packages/ui/src/components/DataTable/table-prefs.ts`

- [ ] **Step 1: Add deps**

In `admin/packages/ui/package.json` `dependencies`:

```json
"@tanstack/react-table": "^8.20.0",
"nuqs": "^2.0.0"
```

```bash
make admin-install
```

- [ ] **Step 2: Public types**

```typescript
// admin/packages/ui/src/components/DataTable/types.ts
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
  onActionOnAllMatching?(ctx: BulkActionContext, action: string): void | Promise<void>;
  /** The action menu. Keyed by `action` string passed back through the callbacks. */
  actions: Array<{ id: string; label: string; destructive?: boolean }>;
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
  /** Override the table id used for column visibility persistence. */
  columnVisibilityCookieKey?: string;
  /** When false, the CSV export button is hidden. */
  exportEnabled?: boolean;
}
```

- [ ] **Step 3: URL state hook**

```tsx
// admin/packages/ui/src/components/DataTable/use-table-url-state.ts
"use client";

import { parseAsInteger, parseAsString, useQueryStates } from "nuqs";
import { useCallback, useMemo } from "react";
import type { Density, SortDirection, TableUrlState } from "./types";

export interface UseTableUrlStateOptions {
  /** Initial sort column. */
  defaultSort?: { column: string; direction: SortDirection };
  /** Initial page size. Must be one of 10, 25, 50, 100. */
  defaultPageSize?: 10 | 25 | 50 | 100;
  /** Initial density. */
  defaultDensity?: Density;
  /** Filter keys the table reads. Other URL keys are ignored. */
  filterKeys?: string[];
}

/**
 * URL-synced table state. Keys: page, pageSize, sort, dir, density, plus
 * any filter key the caller declares.
 */
export function useTableUrlState(
  options: UseTableUrlStateOptions = {},
): TableUrlState {
  const {
    defaultSort,
    defaultPageSize = 25,
    defaultDensity = "default",
    filterKeys = [],
  } = options;

  // Core keys
  const [{ page, pageSize, sort, dir, density }, setCore] = useQueryStates({
    page: parseAsInteger.withDefault(1),
    pageSize: parseAsInteger.withDefault(defaultPageSize),
    sort: parseAsString.withDefault(defaultSort?.column ?? ""),
    dir: parseAsString.withDefault(defaultSort?.direction ?? "desc"),
    density: parseAsString.withDefault(defaultDensity),
  });

  // Build filter key shape dynamically — nuqs's parser is statically typed,
  // but the filter set is open. We use a single record under "filter" prefix.
  const filterParsers = useMemo(() => {
    return Object.fromEntries(
      filterKeys.map((key) => [`f_${key}`, parseAsString.withDefault("")]),
    );
  }, [filterKeys]);

  const [filterRaw, setFiltersRaw] = useQueryStates(filterParsers);

  const filters = useMemo<Record<string, string>>(() => {
    const out: Record<string, string> = {};
    for (const key of filterKeys) {
      const v = (filterRaw as Record<string, string | null>)[`f_${key}`];
      if (v) out[key] = v;
    }
    return out;
  }, [filterKeys, filterRaw]);

  const setPage = useCallback(
    (next: number) => void setCore({ page: Math.max(1, next) }),
    [setCore],
  );
  const setPageSize = useCallback(
    (next: number) => void setCore({ pageSize: next, page: 1 }),
    [setCore],
  );
  const setSort = useCallback(
    (column: string | null, direction: SortDirection) =>
      void setCore({ sort: column ?? "", dir: direction, page: 1 }),
    [setCore],
  );
  const setFilter = useCallback(
    (key: string, value: string | null) =>
      void setFiltersRaw({ [`f_${key}`]: value ?? "" }),
    [setFiltersRaw],
  );
  const setFilters = useCallback(
    (values: Record<string, string | null>) => {
      const next: Record<string, string> = {};
      for (const [key, value] of Object.entries(values)) {
        next[`f_${key}`] = value ?? "";
      }
      void setFiltersRaw(next);
    },
    [setFiltersRaw],
  );
  const setDensity = useCallback(
    (d: Density) => void setCore({ density: d }),
    [setCore],
  );
  const reset = useCallback(() => {
    void setCore({
      page: 1,
      pageSize: defaultPageSize,
      sort: defaultSort?.column ?? "",
      dir: defaultSort?.direction ?? "desc",
    });
    void setFiltersRaw(
      Object.fromEntries(filterKeys.map((k) => [`f_${k}`, ""])),
    );
  }, [defaultPageSize, defaultSort, filterKeys, setCore, setFiltersRaw]);

  return {
    page,
    pageSize,
    sortColumn: sort || null,
    sortDirection: (dir === "asc" ? "asc" : "desc") as SortDirection,
    filters,
    density: (density === "compact" ? "compact" : "default") as Density,
    setPage,
    setPageSize,
    setSort,
    setFilter,
    setFilters,
    setDensity,
    reset,
  };
}
```

- [ ] **Step 4: Preference cookies**

```typescript
// admin/packages/ui/src/components/DataTable/table-prefs.ts
"use client";

import type { Density } from "./types";

const COOKIE_NAME = "sacco_table_prefs";

interface AllPrefs {
  [tableId: string]: {
    hiddenColumns?: string[];
    density?: Density;
  };
}

function readCookie(): AllPrefs {
  if (typeof document === "undefined") return {};
  const raw = document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${COOKIE_NAME}=`));
  if (!raw) return {};
  try {
    return JSON.parse(
      decodeURIComponent(raw.slice(COOKIE_NAME.length + 1)),
    ) as AllPrefs;
  } catch {
    return {};
  }
}

function writeCookie(prefs: AllPrefs): void {
  if (typeof document === "undefined") return;
  document.cookie =
    `${COOKIE_NAME}=${encodeURIComponent(JSON.stringify(prefs))};` +
    `path=/;max-age=${60 * 60 * 24 * 365};SameSite=Strict`;
}

export function getTablePrefs(tableId: string): {
  hiddenColumns: string[];
  density?: Density;
} {
  const all = readCookie();
  return {
    hiddenColumns: all[tableId]?.hiddenColumns ?? [],
    density: all[tableId]?.density,
  };
}

export function setTableHiddenColumns(
  tableId: string,
  hiddenColumns: string[],
): void {
  const all = readCookie();
  all[tableId] = { ...all[tableId], hiddenColumns };
  writeCookie(all);
}

export function setTableDensity(tableId: string, density: Density): void {
  const all = readCookie();
  all[tableId] = { ...all[tableId], density };
  writeCookie(all);
}
```

- [ ] **Step 5: Commit**

```bash
git add admin/packages/ui/package.json \
        admin/packages/ui/src/components/DataTable/{types,use-table-url-state,table-prefs}.ts \
        admin/pnpm-lock.yaml
git commit -m "feat(ui): DataTable types + URL state hook + preference cookies"
```

---

## Task 2: State sub-components + skeleton rows

**Files:**
- Create: `admin/packages/ui/src/components/DataTable/states/{SkeletonRows,EmptyState,FilterEmptyState,ErrorState,PermissionDeniedState}.tsx`

- [ ] **Step 1: Skeleton rows**

```tsx
// admin/packages/ui/src/components/DataTable/states/SkeletonRows.tsx
import { cn } from "../../../utils/cn";

export interface SkeletonRowsProps {
  columnCount: number;
  rowCount?: number;
  density?: "default" | "compact";
}

export function SkeletonRows({
  columnCount,
  rowCount = 8,
  density = "default",
}: SkeletonRowsProps) {
  const heightClass =
    density === "compact"
      ? "h-[var(--height-table-row-compact)]"
      : "h-[var(--height-table-row)]";
  return (
    <>
      {Array.from({ length: rowCount }).map((_, rowIdx) => (
        <tr
          key={`skel-${rowIdx}`}
          className={cn("border-b border-[var(--border-subtle)]", heightClass)}
        >
          {Array.from({ length: columnCount }).map((__, colIdx) => (
            <td key={`skel-${rowIdx}-${colIdx}`} className="px-4">
              <span
                className={cn(
                  "block h-3 w-full max-w-[180px] animate-pulse rounded",
                  "bg-gradient-to-r from-[var(--color-gray-200)] via-[var(--color-gray-100)] to-[var(--color-gray-200)]",
                  "[animation-duration:1.4s]",
                )}
              />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
```

- [ ] **Step 2: Empty state**

```tsx
// admin/packages/ui/src/components/DataTable/states/EmptyState.tsx
import { Inbox } from "lucide-react";
import type { ReactNode } from "react";

export interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <Inbox
        size={48}
        strokeWidth={1.75}
        className="text-[var(--icon-default)]"
        aria-hidden
      />
      <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">
        {title}
      </h3>
      {description ? (
        <p className="max-w-md text-[var(--text-secondary)]">{description}</p>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
```

- [ ] **Step 3: Filter-empty state**

```tsx
// admin/packages/ui/src/components/DataTable/states/FilterEmptyState.tsx
import { SearchX } from "lucide-react";
import { Button } from "../../Button";

export interface FilterEmptyStateProps {
  onClearFilter(): void;
}

export function FilterEmptyState({ onClearFilter }: FilterEmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <SearchX
        size={48}
        strokeWidth={1.75}
        className="text-[var(--icon-default)]"
        aria-hidden
      />
      <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">
        No results match your filter
      </h3>
      <p className="max-w-md text-[var(--text-secondary)]">
        Try adjusting the filter to broaden the result set.
      </p>
      <Button variant="secondary" onClick={onClearFilter}>
        Clear filter
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Error state**

```tsx
// admin/packages/ui/src/components/DataTable/states/ErrorState.tsx
import { AlertOctagon } from "lucide-react";
import { Button } from "../../Button";

export interface ErrorStateProps {
  message: string;
  requestId?: string | null;
  onRetry?(): void;
}

export function ErrorState({ message, requestId, onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <AlertOctagon
        size={48}
        strokeWidth={1.75}
        className="text-[var(--text-danger)]"
        aria-hidden
      />
      <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">
        Something went wrong
      </h3>
      <p className="max-w-md text-[var(--text-secondary)]">{message}</p>
      {requestId ? (
        <p className="text-[12px] text-[var(--text-tertiary)]">
          Request ID: <code>{requestId}</code>
        </p>
      ) : null}
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 5: Permission denied state**

```tsx
// admin/packages/ui/src/components/DataTable/states/PermissionDeniedState.tsx
import { Lock } from "lucide-react";

export function PermissionDeniedState() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <Lock
        size={48}
        strokeWidth={1.75}
        className="text-[var(--icon-default)]"
        aria-hidden
      />
      <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">
        You don't have permission to view this list
      </h3>
      <p className="max-w-md text-[var(--text-secondary)]">
        Contact your administrator if you believe this is wrong.
      </p>
    </div>
  );
}
```

- [ ] **Step 6: Commit**

```bash
git add admin/packages/ui/src/components/DataTable/states/
git commit -m "feat(ui): DataTable state sub-components (skeleton + empty + error + permission)"
```

---

## Task 3: CSV serializer + Toolbar + Pagination + BulkBanner

**Files:**
- Create: `admin/packages/ui/src/components/DataTable/csv.ts`
- Create: `admin/packages/ui/src/components/DataTable/Toolbar.tsx`
- Create: `admin/packages/ui/src/components/DataTable/Pagination.tsx`
- Create: `admin/packages/ui/src/components/DataTable/BulkBanner.tsx`

- [ ] **Step 1: CSV serializer**

```typescript
// admin/packages/ui/src/components/DataTable/csv.ts
/**
 * Serialize rows to RFC-4180-ish CSV. Sufficient for client-side download
 * of small page-sized datasets. Reporting endpoints (sub-plan 29) handle
 * large exports server-side.
 */
export function rowsToCsv(
  rows: Record<string, unknown>[],
  columns: { key: string; header: string }[],
): string {
  const escape = (val: unknown): string => {
    if (val == null) return "";
    const str = String(val);
    if (/[",\n]/.test(str)) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };
  const header = columns.map((c) => escape(c.header)).join(",");
  const body = rows
    .map((row) =>
      columns.map((c) => escape(row[c.key])).join(","),
    )
    .join("\n");
  return `${header}\n${body}\n`;
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
```

- [ ] **Step 2: Pagination**

```tsx
// admin/packages/ui/src/components/DataTable/Pagination.tsx
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "../Button";

export interface PaginationProps {
  page: number; // 1-indexed
  pageSize: number;
  totalRows: number;
  onPageChange(p: number): void;
  onPageSizeChange(size: number): void;
}

export function Pagination({
  page,
  pageSize,
  totalRows,
  onPageChange,
  onPageSizeChange,
}: PaginationProps) {
  const lastPage = Math.max(1, Math.ceil(totalRows / pageSize));
  const firstRow = totalRows === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastRow = Math.min(totalRows, page * pageSize);
  return (
    <div
      className="flex items-center justify-between gap-3 border-t border-[var(--border-subtle)] px-4 py-3 text-[var(--text-secondary)]"
      data-density-target="pagination"
    >
      <div className="text-[13px]">
        Showing <span className="font-medium text-[var(--text-primary)]">{firstRow}</span>
        –<span className="font-medium text-[var(--text-primary)]">{lastRow}</span> of{" "}
        <span className="font-medium text-[var(--text-primary)]">{totalRows}</span>
      </div>
      <div className="flex items-center gap-2">
        <label className="text-[13px]">
          Rows
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="ml-2 h-[var(--height-control-sm)] rounded-[var(--radius-md)] border border-[var(--border-default)] bg-[var(--surface-elevated)] px-2 text-[13px]"
          >
            {[10, 25, 50, 100].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          aria-label="Previous page"
        >
          <ChevronLeft size={16} />
        </Button>
        <span className="text-[13px]">
          Page <span className="font-medium text-[var(--text-primary)]">{page}</span> /{" "}
          {lastPage}
        </span>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= lastPage}
          aria-label="Next page"
        >
          <ChevronRight size={16} />
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: BulkBanner**

```tsx
// admin/packages/ui/src/components/DataTable/BulkBanner.tsx
import { Button } from "../Button";

export interface BulkBannerProps {
  selectedOnPage: number;
  totalMatching: number;
  pageSize: number;
  allMatchingSelected: boolean;
  onSelectAllMatching(): void;
  onClearSelection(): void;
  actions: Array<{ id: string; label: string; destructive?: boolean }>;
  onActionClick(actionId: string): void;
}

export function BulkBanner(props: BulkBannerProps) {
  const {
    selectedOnPage,
    totalMatching,
    pageSize,
    allMatchingSelected,
    onSelectAllMatching,
    onClearSelection,
    actions,
    onActionClick,
  } = props;
  const fullPageSelected = selectedOnPage >= pageSize && totalMatching > pageSize;
  return (
    <div
      className="flex items-center gap-3 border-b border-[var(--border-subtle)] bg-[var(--surface-selected)] px-4 py-2 text-[13px]"
      role="region"
      aria-label="Bulk selection"
    >
      <span className="font-medium text-[var(--text-primary)]">
        {allMatchingSelected
          ? `${totalMatching} matching rows selected`
          : `${selectedOnPage} on this page selected`}
      </span>
      {fullPageSelected && !allMatchingSelected ? (
        <Button size="sm" variant="ghost" onClick={onSelectAllMatching}>
          Select all {totalMatching} matching
        </Button>
      ) : null}
      <Button size="sm" variant="ghost" onClick={onClearSelection}>
        Clear selection
      </Button>
      <div className="ml-auto flex items-center gap-1">
        {actions.map((a) => (
          <Button
            key={a.id}
            size="sm"
            variant={a.destructive ? "destructive" : "secondary"}
            onClick={() => onActionClick(a.id)}
          >
            {a.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Toolbar**

```tsx
// admin/packages/ui/src/components/DataTable/Toolbar.tsx
import { Download, ListFilter, Rows3, Rows4 } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "../Button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "../DropdownMenu";
import type { Density } from "./types";

export interface ToolbarColumn {
  id: string;
  header: string;
  /** Columns marked `pinned` can't be hidden. */
  pinned?: boolean;
}

export interface ToolbarProps {
  filterSlot?: ReactNode;
  density: Density;
  onDensityChange(d: Density): void;
  columns: ToolbarColumn[];
  hiddenColumnIds: string[];
  onToggleColumn(id: string): void;
  onExportCsv?(): void;
}

export function Toolbar({
  filterSlot,
  density,
  onDensityChange,
  columns,
  hiddenColumnIds,
  onToggleColumn,
  onExportCsv,
}: ToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-[var(--border-subtle)] px-4 py-3">
      <div className="flex flex-1 flex-wrap items-center gap-2">{filterSlot}</div>
      <Button
        size="sm"
        variant="ghost"
        onClick={() =>
          onDensityChange(density === "compact" ? "default" : "compact")
        }
        aria-label={
          density === "compact"
            ? "Switch to comfortable density"
            : "Switch to compact density"
        }
      >
        {density === "compact" ? (
          <Rows3 size={16} strokeWidth={1.75} />
        ) : (
          <Rows4 size={16} strokeWidth={1.75} />
        )}
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button size="sm" variant="ghost" aria-label="Column visibility">
            <ListFilter size={16} strokeWidth={1.75} />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-[200px]">
          <DropdownMenuLabel>Columns</DropdownMenuLabel>
          {columns.map((c) => {
            const hidden = hiddenColumnIds.includes(c.id);
            return (
              <DropdownMenuCheckboxItem
                key={c.id}
                checked={!hidden}
                disabled={c.pinned}
                onCheckedChange={() => onToggleColumn(c.id)}
              >
                {c.header}
              </DropdownMenuCheckboxItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
      {onExportCsv ? (
        <Button
          size="sm"
          variant="ghost"
          onClick={onExportCsv}
          aria-label="Export CSV"
        >
          <Download size={16} strokeWidth={1.75} />
        </Button>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add admin/packages/ui/src/components/DataTable/{csv.ts,Toolbar.tsx,Pagination.tsx,BulkBanner.tsx}
git commit -m "feat(ui): DataTable Toolbar + Pagination + BulkBanner + CSV serializer"
```

---

## Task 4: The DataTable component itself

**Files:**
- Create: `admin/packages/ui/src/components/DataTable/DataTable.tsx`
- Create: `admin/packages/ui/src/components/DataTable/index.ts`
- Modify: `admin/packages/ui/src/index.ts`

- [ ] **Step 1: DataTable.tsx**

```tsx
// admin/packages/ui/src/components/DataTable/DataTable.tsx
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
  // Augment columns with a selection column when bulk is enabled
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

  // Column visibility — initialize from cookie
  const initialPrefs = useMemo(() => getTablePrefs(id), [id]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(
    () =>
      Object.fromEntries(
        initialPrefs.hiddenColumns.map((c) => [c, false]),
      ),
  );

  // Persist visibility changes
  useEffect(() => {
    const hidden = Object.entries(columnVisibility)
      .filter(([, v]) => !v)
      .map(([k]) => k);
    setTableHiddenColumns(id, hidden);
  }, [columnVisibility, id]);

  // Persist density (URL state is authoritative; cookie is a default)
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

  // Sort header behaviour — clicking toggles asc/desc/null
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

  // Toolbar config
  const toolbarColumns = useMemo<ToolbarColumn[]>(
    () =>
      userColumns
        .filter((c) => c.id !== undefined)
        .map((c) => ({
          id: c.id!,
          header:
            typeof c.header === "string" ? c.header : (c.id ?? "Column"),
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

  // CSV export — uses currently-visible columns + currently-loaded rows
  const onExportCsv = useCallback(() => {
    const rows = (data ?? []).map((r) => r as unknown as Record<string, unknown>);
    const cols = userColumns
      .filter((c) => c.id && !hiddenColumnIds.includes(c.id))
      .map((c) => ({
        key: c.id!,
        header: typeof c.header === "string" ? c.header : c.id!,
      }));
    downloadCsv(`${id}.csv`, rowsToCsv(rows, cols));
  }, [data, hiddenColumnIds, id, userColumns]);

  // Bulk
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

  // Decide which content state to render
  const isLoading = data === undefined;
  const isPermDenied = state.isPermissionDenied;
  const isError = state.isError;
  const hasFilters = Object.keys(urlState.filters).length > 0;
  const isEmpty = !isLoading && !isError && !isPermDenied && (data ?? []).length === 0;
  const showFilterEmpty = isEmpty && hasFilters;
  const showEmpty = isEmpty && !hasFilters;

  // Density CSS var
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
        onExportCsv={exportEnabled ? onExportCsv : undefined}
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
          requestId={state.error?.requestId ?? undefined}
        />
      ) : showEmpty ? (
        <EmptyState
          title={emptyState.title}
          description={emptyState.description}
          action={emptyState.action}
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
                        onClick={canSort ? () => onSortClick(header.column.id) : undefined}
                      >
                        {flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                        {isSorted ? (urlState.sortDirection === "asc" ? " ▲" : " ▼") : null}
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
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
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
```

- [ ] **Step 2: Index + re-exports**

```typescript
// admin/packages/ui/src/components/DataTable/index.ts
export { DataTable } from "./DataTable";
export { useTableUrlState, type UseTableUrlStateOptions } from "./use-table-url-state";
export type {
  DataTableProps,
  DataTableServerState,
  DataTableEmptyState,
  BulkActionContext,
  BulkActions,
  TableUrlState,
  Density,
  SortDirection,
} from "./types";
```

Append to `admin/packages/ui/src/index.ts`:

```typescript
export * from "./components/DataTable";
```

- [ ] **Step 3: Smoke check**

```bash
cd admin
pnpm --filter @sacco/ui typecheck
```

- [ ] **Step 4: Commit**

```bash
git add admin/packages/ui/src/components/DataTable/{DataTable,index}.{tsx,ts} \
        admin/packages/ui/src/index.ts
git commit -m "feat(ui): DataTable component with server-side sort/filter/pagination + selection"
```

---

## Task 5: Stories + tests

**Files:**
- Create: `admin/packages/ui/src/components/DataTable/DataTable.stories.tsx`
- Create: `admin/packages/ui/src/components/DataTable/csv.test.ts`
- Create: `admin/packages/ui/src/components/DataTable/Pagination.test.tsx`
- Create: `admin/packages/ui/src/components/DataTable/states/EmptyState.test.tsx`

- [ ] **Step 1: Stories**

```tsx
// admin/packages/ui/src/components/DataTable/DataTable.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import type { ColumnDef } from "@tanstack/react-table";
import { useState } from "react";
import { DataTable } from "./DataTable";
import type { TableUrlState } from "./types";

const meta: Meta<typeof DataTable> = {
  title: "Display/DataTable",
  component: DataTable,
  parameters: { layout: "padded" },
};
export default meta;
type Story = StoryObj;

interface SampleRow {
  id: string;
  member: string;
  amount: string;
  status: string;
}

const sampleColumns: ColumnDef<SampleRow>[] = [
  { id: "member", accessorKey: "member", header: "Member" },
  { id: "amount", accessorKey: "amount", header: "Amount" },
  { id: "status", accessorKey: "status", header: "Status" },
];

const sampleData: SampleRow[] = [
  { id: "1", member: "Mary Akello", amount: "UGX 1,234,567", status: "Active" },
  { id: "2", member: "John Mukasa", amount: "UGX 250,000", status: "Dormant" },
  { id: "3", member: "Sarah Achieng", amount: "UGX 5,000,000", status: "Active" },
];

function fakeUrlState(initial: Partial<TableUrlState> = {}): TableUrlState {
  // Storybook-only mock — production uses useTableUrlState.
  const state: TableUrlState = {
    page: 1,
    pageSize: 25,
    sortColumn: null,
    sortDirection: "desc",
    filters: {},
    density: "default",
    setPage: () => {},
    setPageSize: () => {},
    setSort: () => {},
    setFilter: () => {},
    setFilters: () => {},
    setDensity: () => {},
    reset: () => {},
    ...initial,
  };
  return state;
}

export const WithData: Story = {
  render: () => {
    const [urlState] = useState(() => fakeUrlState());
    return (
      <DataTable
        id="story-with-data"
        columns={sampleColumns}
        data={sampleData}
        state={{ totalRows: sampleData.length, isError: false, isPermissionDenied: false }}
        urlState={urlState}
        emptyState={{ title: "No members", description: "Register one to get started." }}
      />
    );
  },
};

export const Loading: Story = {
  render: () => {
    const [urlState] = useState(() => fakeUrlState());
    return (
      <DataTable
        id="story-loading"
        columns={sampleColumns}
        data={undefined}
        state={{ totalRows: 0, isError: false, isPermissionDenied: false }}
        urlState={urlState}
        emptyState={{ title: "No members" }}
      />
    );
  },
};

export const Empty: Story = {
  render: () => {
    const [urlState] = useState(() => fakeUrlState());
    return (
      <DataTable
        id="story-empty"
        columns={sampleColumns}
        data={[]}
        state={{ totalRows: 0, isError: false, isPermissionDenied: false }}
        urlState={urlState}
        emptyState={{
          title: "No members",
          description: "Register your first member to get started.",
        }}
      />
    );
  },
};

export const FilterEmpty: Story = {
  render: () => {
    const [urlState] = useState(() => fakeUrlState({ filters: { name: "ZZZ" } }));
    return (
      <DataTable
        id="story-filter-empty"
        columns={sampleColumns}
        data={[]}
        state={{ totalRows: 0, isError: false, isPermissionDenied: false }}
        urlState={urlState}
        emptyState={{ title: "No members" }}
      />
    );
  },
};

export const Error: Story = {
  render: () => {
    const [urlState] = useState(() => fakeUrlState());
    return (
      <DataTable
        id="story-error"
        columns={sampleColumns}
        data={undefined}
        state={{
          totalRows: 0,
          isError: true,
          isPermissionDenied: false,
          error: {
            message: "The members endpoint returned 503.",
            requestId: "req-abc-123",
          },
        }}
        urlState={urlState}
        emptyState={{ title: "No members" }}
      />
    );
  },
};

export const PermissionDenied: Story = {
  render: () => {
    const [urlState] = useState(() => fakeUrlState());
    return (
      <DataTable
        id="story-perm"
        columns={sampleColumns}
        data={undefined}
        state={{ totalRows: 0, isError: false, isPermissionDenied: true }}
        urlState={urlState}
        emptyState={{ title: "No members" }}
      />
    );
  },
};

export const WithBulk: Story = {
  render: () => {
    const [urlState] = useState(() => fakeUrlState());
    return (
      <DataTable<SampleRow>
        id="story-bulk"
        columns={sampleColumns}
        data={sampleData}
        state={{ totalRows: sampleData.length, isError: false, isPermissionDenied: false }}
        urlState={urlState}
        emptyState={{ title: "No members" }}
        bulk={{
          actions: [
            { id: "export", label: "Export selected" },
            { id: "suspend", label: "Suspend", destructive: true },
          ],
          onActionOnPage: (ctx, a) => alert(`Page action ${a}: ${ctx.selectedIds.length}`),
        }}
      />
    );
  },
};

export const Compact: Story = {
  render: () => {
    const [urlState] = useState(() => fakeUrlState({ density: "compact" }));
    return (
      <DataTable
        id="story-compact"
        columns={sampleColumns}
        data={sampleData}
        state={{ totalRows: sampleData.length, isError: false, isPermissionDenied: false }}
        urlState={urlState}
        emptyState={{ title: "No members" }}
      />
    );
  },
};
```

- [ ] **Step 2: CSV test**

```typescript
// admin/packages/ui/src/components/DataTable/csv.test.ts
import { describe, expect, it } from "vitest";
import { rowsToCsv } from "./csv";

describe("rowsToCsv", () => {
  it("serialises rows with the header line", () => {
    const csv = rowsToCsv(
      [
        { id: "1", member: "Mary Akello" },
        { id: "2", member: "John" },
      ],
      [
        { key: "id", header: "ID" },
        { key: "member", header: "Member" },
      ],
    );
    expect(csv).toBe("ID,Member\n1,Mary Akello\n2,John\n");
  });

  it("escapes commas + newlines + quotes", () => {
    const csv = rowsToCsv(
      [{ note: 'has "quote", and\nnewline' }],
      [{ key: "note", header: "Note" }],
    );
    expect(csv).toContain('"has ""quote"", and\nnewline"');
  });

  it("handles null and undefined", () => {
    const csv = rowsToCsv(
      [{ a: null, b: undefined, c: 0 }],
      [
        { key: "a", header: "A" },
        { key: "b", header: "B" },
        { key: "c", header: "C" },
      ],
    );
    expect(csv).toContain(",,0");
  });
});
```

- [ ] **Step 3: Pagination test**

```tsx
// admin/packages/ui/src/components/DataTable/Pagination.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Pagination } from "./Pagination";

describe("Pagination", () => {
  it("renders showing range correctly", () => {
    render(
      <Pagination
        page={2}
        pageSize={25}
        totalRows={120}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
      />,
    );
    expect(screen.getByText("26")).toBeInTheDocument();
    expect(screen.getByText("50")).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument();
  });

  it("fires onPageChange when next clicked", async () => {
    const onPageChange = vi.fn();
    const user = userEvent.setup();
    render(
      <Pagination
        page={1}
        pageSize={25}
        totalRows={120}
        onPageChange={onPageChange}
        onPageSizeChange={() => {}}
      />,
    );
    await user.click(screen.getByLabelText("Next page"));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("disables prev on first page", () => {
    render(
      <Pagination
        page={1}
        pageSize={25}
        totalRows={120}
        onPageChange={() => {}}
        onPageSizeChange={() => {}}
      />,
    );
    expect(screen.getByLabelText("Previous page")).toBeDisabled();
  });
});
```

- [ ] **Step 4: EmptyState test**

```tsx
// admin/packages/ui/src/components/DataTable/states/EmptyState.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("renders title + description + action slot", () => {
    render(
      <EmptyState
        title="No members"
        description="Get started by adding one."
        action={<button>Add member</button>}
      />,
    );
    expect(screen.getByText("No members")).toBeInTheDocument();
    expect(screen.getByText("Get started by adding one.")).toBeInTheDocument();
    expect(screen.getByText("Add member")).toBeInTheDocument();
  });
});
```

- [ ] **Step 5: Run + commit**

```bash
cd admin
pnpm --filter @sacco/ui test
pnpm --filter @sacco/ui storybook:build
```

```bash
git add admin/packages/ui/src/components/DataTable/
git commit -m "feat(ui): DataTable Storybook stories + tests"
```

---

## Task 6: CLAUDE.md contract

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append contract T**

In `CLAUDE.md`, under `### Admin portal contracts (do not violate)`, append:

```markdown
T. Every list screen in the portal renders through `<DataTable>` from
   `@sacco/ui`. Server-side pagination, sort, and filter; URL-synced
   state via `useTableUrlState`. Hand-rolling a `<table>` for a list of
   records is a contract violation. The five visual states
   (data / loading / empty / filter-empty / error / permission-denied)
   are handled by the component; consumers configure them via props.
   Column visibility and density persist per-user via the
   `sacco_table_prefs` cookie. CSV export is client-side from the loaded
   page; large-dataset CSV is a reporting endpoint, not a table export.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): contract T — every list screen uses DataTable"
```

---

## Task 7: Final verification

- [ ] **Step 1: Full pipeline**

```bash
cd admin
pnpm install
pnpm typecheck
pnpm lint
pnpm test
pnpm --filter @sacco/ui storybook:build
```
Expected: green.

- [ ] **Step 2: Visual smoke via Storybook**

```bash
cd admin
pnpm --filter @sacco/ui storybook &
SB_PID=$!
sleep 12
# Open http://localhost:6006 → Display/DataTable
# Verify: WithData, Loading, Empty, FilterEmpty, Error, PermissionDenied,
# WithBulk, Compact all render correctly.
kill $SB_PID 2>/dev/null || true
```

- [ ] **Step 3: PR**

```bash
git push -u origin feat/portal-v1/10-datatable
gh pr create --title "feat(ui): DataTable wrapper (server-side pagination + states + bulk + CSV)" --body "$(cat <<'EOF'
## Summary
- `<DataTable>` in `@sacco/ui` wrapping TanStack Table v8 in server-side ("manual") mode
- `useTableUrlState` hook: page / pageSize / sort / dir / density / filter keys all sync to URL via nuqs
- Cookie-backed preferences (`sacco_table_prefs`): per-table column visibility + density default
- Five visual states: data, loading (skeleton rows), empty (with action slot), filter-empty (with clear-filter affordance), error (with `request_id`), permission-denied
- Bulk selection: page-only checkbox + separate "Select all N matching" banner; consumer-defined actions
- Sticky header + sticky first column (CSS-only)
- Client-side CSV export from the loaded page (large datasets stay on reporting endpoints, sub-plan 29)
- Toolbar: filter slot + density toggle + column visibility + CSV export buttons
- Pagination with rows/page selector and prev/next
- Storybook covers all states + density variants
- CLAUDE.md contract T: every list screen uses `<DataTable>`

## Out of scope
- Form primitives (sub-plan 11) — DataTable doesn't ship inputs; consumers wire their own filter forms into the `filterSlot`
- DataTable usage in feature modules — those start landing from sub-plan 12

## Test plan
- [ ] `pnpm --filter @sacco/ui test` (CSV serializer, Pagination, EmptyState)
- [ ] `pnpm --filter @sacco/ui storybook:build` succeeds
- [ ] Visual smoke against all eight stories

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] `@tanstack/react-table` + `nuqs` added to `@sacco/ui` deps
- [ ] `useTableUrlState` syncs page, pageSize, sort, density, and filter keys to URL
- [ ] `sacco_table_prefs` cookie persists per-table column visibility + density
- [ ] `<DataTable>` renders all five non-error states correctly per the design system
- [ ] Bulk selection works at page level + offers "select all matching" when page is fully selected
- [ ] Toolbar exposes density toggle, column visibility menu, CSV export
- [ ] Client-side CSV export downloads with the table's `id` as the filename
- [ ] Storybook stories: WithData, Loading, Empty, FilterEmpty, Error, PermissionDenied, WithBulk, Compact
- [ ] CLAUDE.md gains contract T
- [ ] All new tests pass
- [ ] PR opened, CI green

## Notes for the executing subagent

- **Do not** add client-side sorting or filtering. The contract is server-side everything. If a feature needs client-side filtering, it's a different component, not this one.
- **Do not** add a global "select all matching" without the consumer's explicit `onActionOnAllMatching` callback. The DataTable doesn't know what "matching" means against the server.
- **Do not** ship a built-in filter component. The `filterSlot` is intentionally a slot — each feature module passes its own filter inputs (search box, status dropdown, date range, etc.) that map to its `filterKeys`.
- **Do not** introduce a `loading` prop. The `data === undefined` convention is the source of truth — that lets TanStack Query's `data` flow straight through.
- **Do not** add row click handlers or hover affordances beyond the design system's "row hover bg-surface-hover". Row-level actions belong in the action cell or the row's `cell` renderer.
- The bulk banner only appears when at least one row is selected. The "Select all N matching" button only appears once the current page is fully selected AND `totalMatching > pageSize`. Both behaviours are required by the design system §"Data Tables" — don't simplify.
- The CSV export covers the LOADED page only, with VISIBLE columns. The button name is intentionally not "Export all" — that lives on reporting endpoints. If a feature needs a real export, it should send the user to the matching report.
- Sticky first column is a CSS pattern (`position: sticky; left: 0; z-index: 1`). It's not enabled by default — feature modules opt in by adding `position: sticky` styles to their first column's `meta`. Until a consumer needs it, this is documented behaviour, not implemented behaviour.
- The skeleton row count defaults to 8, which matches the average list page on a 1080p screen. Don't loop more — over-loading skeleton rows blows up jank.
- The density toggle changes `--row-h` CSS var. The same CSS var drives skeleton row height so loading state matches the loaded state visually.
- Column visibility persistence is per-user via cookie. If the user switches browsers, their preferences don't follow. A future enhancement could sync via tenant settings; not in v1.
- The `getRowId: (row) => row.id` config is required so selection survives data changes (e.g., after pagination). Every table's `TData` must extend `{ id: string }`. The type constraint enforces this.
- If `pnpm --filter @sacco/ui test` complains about `@tanstack/react-table` and React 19, you may need to install with `--force` once. Both packages declare loose React peer dep ranges that align eventually.
