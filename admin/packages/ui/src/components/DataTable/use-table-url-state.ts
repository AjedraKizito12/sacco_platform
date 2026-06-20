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
  /**
   * nuqs routing mode. `true` (default) updates the URL client-side only —
   * right for in-memory tables. `false` does a real navigation so a Server
   * Component re-runs (its searchParams change), enabling true server-side
   * pagination. Existing in-memory callers omit this and keep `true`.
   */
  shallow?: boolean;
}

/**
 * URL-synced table state. Keys: page, pageSize, sort, dir, density, plus
 * any filter key the caller declares (prefixed with `f_`).
 */
export function useTableUrlState(
  options: UseTableUrlStateOptions = {},
): TableUrlState {
  const {
    defaultSort,
    defaultPageSize = 25,
    defaultDensity = "default",
    filterKeys = [],
    shallow = true,
  } = options;

  const [{ page, pageSize, sort, dir, density }, setCore] = useQueryStates(
    {
      page: parseAsInteger.withDefault(1),
      pageSize: parseAsInteger.withDefault(defaultPageSize),
      sort: parseAsString.withDefault(defaultSort?.column ?? ""),
      dir: parseAsString.withDefault(defaultSort?.direction ?? "desc"),
      density: parseAsString.withDefault(defaultDensity),
    },
    { shallow },
  );

  const filterParsers = useMemo(() => {
    return Object.fromEntries(
      filterKeys.map((key) => [`f_${key}`, parseAsString.withDefault("")]),
    );
  }, [filterKeys]);

  const [filterRaw, setFiltersRaw] = useQueryStates(filterParsers, { shallow });

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
    (key: string, value: string | null) => {
      void setFiltersRaw({ [`f_${key}`]: value ?? "" });
      void setCore({ page: 1 });
    },
    [setFiltersRaw, setCore],
  );
  const setFilters = useCallback(
    (values: Record<string, string | null>) => {
      const next: Record<string, string> = {};
      for (const [key, value] of Object.entries(values)) {
        next[`f_${key}`] = value ?? "";
      }
      void setFiltersRaw(next);
      void setCore({ page: 1 });
    },
    [setFiltersRaw, setCore],
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
