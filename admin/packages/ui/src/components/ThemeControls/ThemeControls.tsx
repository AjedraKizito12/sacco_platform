"use client";

import { Moon, Monitor, Sun } from "lucide-react";
import type { ThemeAccent, ThemeFontSize, ThemeMode, ThemePrefs } from "@sacco/schemas";
import { THEME_ACCENTS, THEME_FONT_SIZES } from "@sacco/schemas";

import { cn } from "../../utils/cn";

export { ThemeModeToggle, type ThemeModeToggleProps } from "./ThemeModeToggle";

const MODE_OPTIONS: { value: ThemeMode; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

// "XL" (not "Extra-large") so its accessible name doesn't collide with the
// "Large" button under a case-insensitive /large/i substring match.
const FONT_SIZE_LABEL: Record<ThemeFontSize, string> = {
  compact: "Compact",
  default: "Default",
  large: "Large",
  xl: "XL",
};

const ACCENT_LABEL: Record<ThemeAccent, string> = {
  default: "Default",
  blue: "Blue",
  green: "Green",
  amber: "Amber",
  slate: "Slate",
};

/**
 * SANCTIONED EXCEPTION to Contract Q (no hardcoded theme colors in
 * component code): this is the one place a fixed hex map is allowed.
 * These swatches exist to let the operator SEE each accent's brand
 * color before selecting it. The real accent ramps only exist as CSS
 * custom properties scoped under `:root[data-accent="..."]` — a swatch
 * nested inside the (unswitched) picker itself cannot read the ramp for
 * an accent that isn't currently active, so there is no token that can
 * drive this fill. Values are the `--color-brand-500` stop of each
 * ramp in tokens.css; keep them in sync if that file's palette changes.
 */
const ACCENT_SWATCH: Record<ThemeAccent, string> = {
  default: "#7C5CF0",
  blue: "#3B82F6",
  green: "#10B981",
  amber: "#F59E0B",
  slate: "#64748B",
};

function segmentButtonClasses(pressed: boolean) {
  return cn(
    "inline-flex items-center gap-2 rounded-[var(--radius-md)] px-3 py-2",
    "text-[length:var(--text-body)] font-medium transition-colors duration-150",
    "border",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--border-focus)]",
    pressed
      ? [
          "border-[var(--interactive-primary-bg)]",
          "bg-[var(--interactive-primary-bg)]",
          "text-[color:var(--interactive-primary-text)]",
        ]
      : [
          "border-[var(--border-default)]",
          "bg-[var(--surface-elevated)]",
          "text-[var(--text-secondary)]",
          "hover:bg-[var(--surface-hover)]",
          "hover:text-[var(--text-primary)]",
        ],
  );
}

export interface ThemeControlsProps {
  value: ThemePrefs;
  onChange: (next: ThemePrefs) => void;
  className?: string;
}

/**
 * Presentational theme preferences picker: mode, accent, and font-size
 * groups. State is owned by the caller — this component only reports
 * intent via `onChange({ ...value, <field>: next })`.
 */
export function ThemeControls({ value, onChange, className }: ThemeControlsProps) {
  return (
    <div className={cn("flex flex-col gap-6", className)}>
      <fieldset className="flex flex-col gap-2">
        <legend className="text-[length:var(--text-body)] font-medium text-[var(--text-primary)]">
          Mode
        </legend>
        <div role="group" aria-label="Theme mode" className="flex flex-wrap gap-2">
          {MODE_OPTIONS.map(({ value: mode, label, icon: Icon }) => {
            const pressed = value.mode === mode;
            return (
              <button
                key={mode}
                type="button"
                aria-pressed={pressed}
                onClick={() => onChange({ ...value, mode })}
                className={segmentButtonClasses(pressed)}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {label}
              </button>
            );
          })}
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-[length:var(--text-body)] font-medium text-[var(--text-primary)]">
          Accent
        </legend>
        <div role="group" aria-label="Theme accent" className="flex flex-wrap gap-2">
          {THEME_ACCENTS.map((accent) => {
            const pressed = value.accent === accent;
            return (
              <button
                key={accent}
                type="button"
                aria-pressed={pressed}
                aria-label={ACCENT_LABEL[accent]}
                title={ACCENT_LABEL[accent]}
                onClick={() => onChange({ ...value, accent })}
                className={cn(
                  "flex h-9 w-9 items-center justify-center rounded-[var(--radius-full)]",
                  "border-2 transition-colors duration-150",
                  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--border-focus)]",
                  pressed ? "border-[var(--border-focus)]" : "border-transparent",
                )}
              >
                <span
                  aria-hidden="true"
                  className="block h-6 w-6 rounded-[var(--radius-full)] border border-[var(--border-default)]"
                  // ACCENT_SWATCH is the sanctioned exception documented above.
                  style={{ backgroundColor: ACCENT_SWATCH[accent] }}
                />
              </button>
            );
          })}
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-[length:var(--text-body)] font-medium text-[var(--text-primary)]">
          Font size
        </legend>
        <div role="group" aria-label="Theme font size" className="flex flex-wrap gap-2">
          {THEME_FONT_SIZES.map((fontSize) => {
            const pressed = value.fontSize === fontSize;
            return (
              <button
                key={fontSize}
                type="button"
                aria-pressed={pressed}
                onClick={() => onChange({ ...value, fontSize })}
                className={segmentButtonClasses(pressed)}
              >
                {FONT_SIZE_LABEL[fontSize]}
              </button>
            );
          })}
        </div>
      </fieldset>
    </div>
  );
}
