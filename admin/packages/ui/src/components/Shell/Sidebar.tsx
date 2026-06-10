import type { ReactNode } from "react";
import { cn } from "../../utils/cn";

export interface SidebarGroup {
  /** Optional group heading (omit for ungrouped items). */
  label?: string;
  items: ReactNode;
}

export interface SidebarProps {
  groups: SidebarGroup[];
  collapsed?: boolean;
  className?: string;
}

export function Sidebar({ groups, collapsed, className }: SidebarProps) {
  return (
    <aside
      className={cn(
        "sticky top-[var(--height-header)] h-[calc(100vh-var(--height-header))]",
        "flex flex-col border-r border-[var(--border-subtle)] bg-[var(--surface-elevated)]",
        "py-3",
        collapsed
          ? "w-[var(--width-sidebar-collapsed)]"
          : "w-[var(--width-sidebar)]",
        className,
      )}
      aria-label="Primary"
    >
      {groups.map((group, idx) => (
        <div
          key={group.label ?? `group-${idx}`}
          className={cn("flex flex-col gap-0.5 px-3 py-2", idx > 0 && "mt-2")}
        >
          {!collapsed && group.label ? (
            <p className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">
              {group.label}
            </p>
          ) : null}
          <nav className="flex flex-col gap-0.5">{group.items}</nav>
        </div>
      ))}
    </aside>
  );
}
