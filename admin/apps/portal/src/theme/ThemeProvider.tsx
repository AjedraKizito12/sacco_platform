"use client";

import { createContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { ThemePrefs } from "@sacco/schemas";
import { writeThemeCookieClient } from "./theme-cookie";

export interface ThemeContextValue {
  prefs: ThemePrefs;
  setPrefs: (next: ThemePrefs) => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

/**
 * Pure — exported for direct unit testing (no DOM globals beyond the
 * element passed in). Stamps `data-theme` on `el`, resolving "system" via
 * the caller-supplied `systemDark` flag. `data-accent` / `data-font-size`
 * are set only for non-default values and removed otherwise, so the base
 * `:root` token values apply.
 */
export function applyThemeAttributes(
  el: HTMLElement,
  prefs: ThemePrefs,
  systemDark: boolean,
): void {
  const resolvedTheme = prefs.mode === "system" ? (systemDark ? "dark" : "light") : prefs.mode;
  el.setAttribute("data-theme", resolvedTheme);

  if (prefs.accent !== "default") {
    el.setAttribute("data-accent", prefs.accent);
  } else {
    el.removeAttribute("data-accent");
  }

  if (prefs.fontSize !== "default") {
    el.setAttribute("data-font-size", prefs.fontSize);
  } else {
    el.removeAttribute("data-font-size");
  }
}

export interface ThemeProviderProps {
  initial: ThemePrefs;
  children: ReactNode;
}

export function ThemeProvider({ initial, children }: ThemeProviderProps) {
  const [prefs, setPrefsState] = useState<ThemePrefs>(initial);
  // Keep the latest prefs available to the matchMedia listener without
  // re-subscribing it on every prefs change.
  const prefsRef = useRef(prefs);
  prefsRef.current = prefs;

  const setPrefs = (next: ThemePrefs) => {
    setPrefsState(next);
    writeThemeCookieClient(next);
    if (typeof document !== "undefined") {
      const systemDark =
        typeof window !== "undefined"
          ? window.matchMedia("(prefers-color-scheme: dark)").matches
          : false;
      applyThemeAttributes(document.documentElement, next, systemDark);
    }
  };

  // Apply on mount so the client render matches whatever the pre-paint
  // inline script already stamped (system resolution may differ if the
  // cookie was absent server-side vs. present client-side).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    applyThemeAttributes(document.documentElement, prefsRef.current, systemDark);
  }, []);

  // Re-apply on OS scheme changes while mode === "system".
  useEffect(() => {
    if (typeof window === "undefined") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const listener = (e: MediaQueryListEvent) => {
      if (prefsRef.current.mode !== "system") return;
      applyThemeAttributes(document.documentElement, prefsRef.current, e.matches);
    };
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, []);

  return <ThemeContext.Provider value={{ prefs, setPrefs }}>{children}</ThemeContext.Provider>;
}
