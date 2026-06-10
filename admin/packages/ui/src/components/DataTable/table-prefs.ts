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
  const entry = all[tableId];
  const result: { hiddenColumns: string[]; density?: Density } = {
    hiddenColumns: entry?.hiddenColumns ?? [],
  };
  if (entry?.density) result.density = entry.density;
  return result;
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
