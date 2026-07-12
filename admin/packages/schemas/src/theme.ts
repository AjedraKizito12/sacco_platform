import { z } from "zod";

export type ThemeMode = "light" | "dark" | "system";
export type ThemeAccent = "default" | "blue" | "green" | "amber" | "slate";
export type ThemeFontSize = "compact" | "default" | "large" | "xl";

export interface ThemePrefs {
  mode: ThemeMode;
  accent: ThemeAccent;
  fontSize: ThemeFontSize;
}

export const THEME_ACCENTS = ["default", "blue", "green", "amber", "slate"] as const;
export const THEME_FONT_SIZES = ["compact", "default", "large", "xl"] as const;

export const THEME_DEFAULTS: ThemePrefs = {
  mode: "system",
  accent: "default",
  fontSize: "default",
};

export const themePrefsSchema = z.object({
  mode: z.enum(["light", "dark", "system"]).catch(THEME_DEFAULTS.mode),
  accent: z.enum(THEME_ACCENTS).catch(THEME_DEFAULTS.accent),
  fontSize: z.enum(THEME_FONT_SIZES).catch(THEME_DEFAULTS.fontSize),
});

export function parseThemeCookie(raw: string | undefined): ThemePrefs {
  if (!raw) return { ...THEME_DEFAULTS };
  try {
    return themePrefsSchema.parse(JSON.parse(raw));
  } catch {
    return { ...THEME_DEFAULTS };
  }
}

export function serializeThemePrefs(p: ThemePrefs): string {
  return JSON.stringify(p);
}
