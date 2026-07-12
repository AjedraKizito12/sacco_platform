"use client";

import { Card, ThemeControls } from "@sacco/ui";
import { useTheme } from "@/theme/useTheme";

/**
 * Shared appearance-picker body reused by all three audience surfaces
 * (platform settings, tenant settings, member profile). State is owned by
 * `ThemeProvider` (root layout) via `useTheme()` — this component only
 * renders the picker and reports intent through `setPrefs`.
 */
export function AppearanceSection() {
  const { prefs, setPrefs } = useTheme();

  return (
    <Card className="flex max-w-2xl flex-col gap-4 p-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-[length:var(--text-h5)] font-semibold text-[var(--text-primary)]">
          Appearance
        </h2>
        <p className="text-[length:var(--text-small)] text-[var(--text-secondary)]">
          Choose how the portal looks on this device — theme mode, accent color, and text size.
        </p>
      </div>
      <ThemeControls value={prefs} onChange={setPrefs} />
    </Card>
  );
}
