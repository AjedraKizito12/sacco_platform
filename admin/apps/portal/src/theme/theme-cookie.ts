// Client-safe helpers for the `sacco_theme` cookie. Mirrors the shape of
// `admin/packages/ui/src/components/DataTable/table-prefs.ts`: JSON payload,
// encodeURIComponent'd, not httpOnly (the pre-paint inline script and client
// components both need to read/write it).
//
// MUST NOT import `next/headers` (or anything that does) — this file is
// imported by `"use client"` code (`ThemeProvider.tsx`), and Next's
// server-only guard on `next/headers` is enforced at module level. The
// server-side reader lives in `./theme-cookie.server.ts` instead.

import { serializeThemePrefs, type ThemePrefs } from "@sacco/schemas";

export const THEME_COOKIE = "sacco_theme";

/**
 * Client-side write via `document.cookie`. Not httpOnly — the pre-paint
 * inline script (`theme-script.ts`) must be able to read it before React
 * hydrates.
 */
export function writeThemeCookieClient(p: ThemePrefs): void {
  if (typeof document === "undefined") return;
  document.cookie =
    `${THEME_COOKIE}=${encodeURIComponent(serializeThemePrefs(p))};` +
    `path=/;max-age=${60 * 60 * 24 * 365};SameSite=Lax`;
}
