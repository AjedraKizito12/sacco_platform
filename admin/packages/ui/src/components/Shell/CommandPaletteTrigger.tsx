import { Search } from "lucide-react";
import { cn } from "../../utils/cn";

export interface CommandPaletteTriggerProps {
  onActivate(): void;
  className?: string;
}

export function CommandPaletteTrigger({
  onActivate,
  className,
}: CommandPaletteTriggerProps) {
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
