// Server + client helpers for the `sacco_theme` cookie. Mirrors the shape of
// `admin/packages/ui/src/components/DataTable/table-prefs.ts`: JSON payload,
// encodeURIComponent'd, not httpOnly (the pre-paint inline script and client
// components both need to read/write it).

import { cookies } from "next/headers";
import { parseThemeCookie, serializeThemePrefs, type ThemePrefs } from "@sacco/schemas";

export const THEME_COOKIE = "sacco_theme";

/**
 * Server-side read. Used by the root layout to stamp the initial `data-*`
 * attributes on `<html>` and to seed `<ThemeProvider initial={...}>` so the
 * client render matches the server render (no hydration mismatch).
 */
export async function getServerThemePrefs(): Promise<ThemePrefs> {
  const jar = await cookies();
  return parseThemeCookie(jar.get(THEME_COOKIE)?.value);
}

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
