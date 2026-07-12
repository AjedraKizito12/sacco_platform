"use client";

import { Moon, Monitor, Sun } from "lucide-react";
import type { ThemeMode } from "@sacco/schemas";

import { cn } from "../../utils/cn";

const MODE_CYCLE: Record<ThemeMode, ThemeMode> = {
  light: "dark",
  dark: "system",
  system: "light",
};

const MODE_ICON: Record<ThemeMode, typeof Sun> = {
  light: Sun,
  dark: Moon,
  system: Monitor,
};

const MODE_LABEL: Record<ThemeMode, string> = {
  light: "Light",
  dark: "Dark",
  system: "System",
};

export interface ThemeModeToggleProps {
  value: ThemeMode;
  onChange: (next: ThemeMode) => void;
  className?: string;
}

/**
 * Compact icon button that cycles through theme modes: light → dark →
 * system → light. Shows the icon for the CURRENT mode; clicking advances
 * to the next one in the cycle.
 */
export function ThemeModeToggle({ value, onChange, className }: ThemeModeToggleProps) {
  const Icon = MODE_ICON[value];

  return (
    <button
      type="button"
      aria-label={`Theme: ${MODE_LABEL[value]}. Click to switch mode.`}
      onClick={() => onChange(MODE_CYCLE[value])}
      className={cn(
        "inline-flex h-[var(--height-control-sm)] w-[var(--height-control-sm)] items-center justify-center",
        "rounded-[var(--radius-md)] border border-[var(--border-default)]",
        "bg-[var(--surface-elevated)] text-[var(--text-secondary)]",
        "transition-colors duration-150",
        "hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--border-focus)]",
        className,
      )}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
    </button>
  );
}
