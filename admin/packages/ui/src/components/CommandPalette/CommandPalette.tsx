"use client";

import { Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Dialog, DialogContent, DialogTitle } from "../Dialog";
import { cn } from "../../utils/cn";

export interface CommandPaletteItem {
  id: string;
  title: string;
  subtitle: string;
  url: string;
  group: string;
}

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange(open: boolean): void;
  query: string;
  onQueryChange(q: string): void;
  items: CommandPaletteItem[];
  loading?: boolean;
  onSelect(item: CommandPaletteItem): void;
  emptyLabel?: string;
  placeholder?: string;
}

interface Group {
  label: string;
  items: CommandPaletteItem[];
}

function groupItems(items: CommandPaletteItem[]): Group[] {
  const order: string[] = [];
  const by = new Map<string, CommandPaletteItem[]>();
  for (const item of items) {
    if (!by.has(item.group)) {
      by.set(item.group, []);
      order.push(item.group);
    }
    by.get(item.group)!.push(item);
  }
  return order.map((label) => ({ label, items: by.get(label)! }));
}

export function CommandPalette({
  open,
  onOpenChange,
  query,
  onQueryChange,
  items,
  loading = false,
  onSelect,
  emptyLabel = "No results",
  placeholder = "Search…",
}: CommandPaletteProps) {
  const [active, setActive] = useState(0);
  const groups = useMemo(() => groupItems(items), [items]);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reset the active row whenever the result set changes.
  useEffect(() => {
    setActive(0);
  }, [items]);

  // Focus the input when the palette opens (avoids the autoFocus a11y pitfall).
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (items.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = items[active];
      if (item) onSelect(item);
    }
  }

  const showEmpty = !loading && query.trim().length > 0 && items.length === 0;
  let flatIndex = -1;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[12%] w-full max-w-xl translate-y-0 gap-0 overflow-hidden p-0">
        <DialogTitle className="sr-only">Search</DialogTitle>
        <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-4">
          <Search size={16} strokeWidth={1.75} aria-hidden className="text-[var(--icon-default)]" />
          <input
            ref={inputRef}
            type="text"
            aria-label="Search"
            value={query}
            placeholder={placeholder}
            onChange={(e) => onQueryChange(e.target.value)}
            onKeyDown={onKeyDown}
            className="h-11 w-full bg-transparent text-[var(--text-primary)] outline-none placeholder:text-[var(--text-tertiary)]"
          />
        </div>
        <div className="max-h-80 overflow-y-auto py-2">
          {loading ? (
            <div className="px-4 py-3 text-sm text-[var(--text-secondary)]">Searching…</div>
          ) : showEmpty ? (
            <div className="px-4 py-3 text-sm text-[var(--text-secondary)]">{emptyLabel}</div>
          ) : (
            groups.map((group) => (
              <div key={group.label}>
                <div className="px-4 py-1 text-[11px] font-medium uppercase tracking-wide text-[var(--text-tertiary)]">
                  {group.label}
                </div>
                {group.items.map((item) => {
                  flatIndex += 1;
                  const isActive = flatIndex === active;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => onSelect(item)}
                      data-active={isActive || undefined}
                      className={cn(
                        "flex w-full flex-col items-start px-4 py-2 text-left",
                        isActive
                          ? "bg-[var(--surface-hover)]"
                          : "hover:bg-[var(--surface-hover)]",
                      )}
                    >
                      <span className="text-sm text-[var(--text-primary)]">{item.title}</span>
                      <span className="text-xs text-[var(--text-secondary)]">{item.subtitle}</span>
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
