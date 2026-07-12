"use client";

import { ThemeModeToggle } from "@sacco/ui";
import { useTheme } from "@/theme/useTheme";

/**
 * Compact header quick-toggle for theme mode. Lives in the shared
 * `AppShellHeader`, so it renders across all three portal variants
 * (platform, tenant, member). Accent / font-size stay picker-only,
 * reachable from the full `AppearanceSection` surfaces.
 */
export function AppShellThemeToggle() {
  const { prefs, setPrefs } = useTheme();

  return (
    <ThemeModeToggle
      value={prefs.mode}
      onChange={(mode) => setPrefs({ ...prefs, mode })}
    />
  );
}
