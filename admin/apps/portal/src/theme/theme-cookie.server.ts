// Server-only helper for the `sacco_theme` cookie. Uses `next/headers`,
// which Next enforces as a server-only module at MODULE level — importing
// this file from any `"use client"` file (even transitively) drags
// `next/headers` into the client bundle and breaks the build. Import this
// ONLY from server components (currently: the root layout). Client code
// must use `./theme-cookie` (no `next/headers` import) instead.
//
// Mirrors `admin/apps/portal/src/auth/cookies.ts`, which is never imported
// by a `"use client"` file.

import { cookies } from "next/headers";
import { parseThemeCookie, type ThemePrefs } from "@sacco/schemas";
import { THEME_COOKIE } from "./theme-cookie";

/**
 * Server-side read. Used by the root layout to stamp the initial `data-*`
 * attributes on `<html>` and to seed `<ThemeProvider initial={...}>` so the
 * client render matches the server render (no hydration mismatch).
 */
export async function getServerThemePrefs(): Promise<ThemePrefs> {
  const jar = await cookies();
  return parseThemeCookie(jar.get(THEME_COOKIE)?.value);
}
