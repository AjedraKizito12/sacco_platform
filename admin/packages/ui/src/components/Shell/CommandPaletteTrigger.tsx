import { Search } from "lucide-react";
import { cn } from "../../utils/cn";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../Tooltip";

export interface CommandPaletteTriggerProps {
  onActivate(): void;
  className?: string;
  /**
   * Renders the trigger disabled with a "coming soon" tooltip and no ⌘K hint.
   * Use until a real command palette / search backend is wired — advertising an
   * interactive search box that does nothing is worse than showing it's pending.
   */
  disabled?: boolean;
}

export function CommandPaletteTrigger({
  onActivate,
  className,
  disabled = false,
}: CommandPaletteTriggerProps) {
  if (disabled) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              disabled
              aria-label="Search (coming soon)"
              className={cn(
                "inline-flex h-[var(--height-control-sm)] items-center gap-2 rounded-[var(--radius-md)]",
                "border border-[var(--border-default)] bg-[var(--surface-elevated)] px-3",
                "text-[13px] text-[var(--text-tertiary)]",
                "cursor-not-allowed opacity-60",
                className,
              )}
            >
              <Search size={14} strokeWidth={1.75} aria-hidden />
              <span>Search…</span>
            </button>
          </TooltipTrigger>
          <TooltipContent>Search coming soon</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return (
    <button
      type="button"
      onClick={onActivate}
      className={cn(
        "inline-flex h-[var(--height-control-sm)] items-center gap-2 rounded-[var(--radius-md)]",
        "border border-[var(--border-default)] bg-[var(--surface-elevated)] px-3",
        "text-[13px] text-[var(--text-tertiary)]",
        "hover:border-[var(--border-strong)] hover:text-[var(--text-secondary)]",
        "focus-visible:outline-2 focus-visible:outline-[var(--border-focus)]",
        className,
      )}
      aria-label="Open command palette"
    >
      <Search size={14} strokeWidth={1.75} aria-hidden />
      <span>Search…</span>
      <span className="ml-4 inline-flex items-center gap-1 rounded border border-[var(--border-subtle)] px-1.5 py-0.5 text-[11px]">
        <kbd className="font-sans">⌘</kbd>
        <kbd className="font-sans">K</kbd>
      </span>
    </button>
  );
}
