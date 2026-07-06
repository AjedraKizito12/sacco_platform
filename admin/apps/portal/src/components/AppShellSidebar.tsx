"use client";

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { cn } from "@sacco/ui";
import { navForVariant, type ShellVariant } from "./shell/nav-config";
import { SidebarNav } from "./shell/SidebarNav";

interface AppShellSidebarProps {
  variant: ShellVariant;
  /** Icons-only rail when true. */
  collapsed?: boolean;
  /** Toggle handler — when omitted (or canToggle false) no toggle renders. */
  onToggle?: () => void;
  canToggle?: boolean;
}

export function AppShellSidebar({
  variant,
  collapsed = false,
  onToggle,
  canToggle = true,
}: AppShellSidebarProps) {
  const groups = navForVariant(variant);
  return (
    <aside
      className={cn(
        "sticky top-[var(--height-header)] z-[var(--z-sticky)] h-[calc(100vh-var(--height-header))] shrink-0",
        "flex flex-col border-r border-[var(--border-subtle)] bg-[var(--surface-elevated)]",
        "transition-[width] duration-200 ease-[var(--ease-out)]",
        collapsed
          ? "w-[var(--width-sidebar-collapsed)]"
          : "w-[var(--width-sidebar)]",
      )}
      aria-label="Primary navigation"
    >
      <div
        className={cn(
          "flex-1 overflow-y-auto overflow-x-hidden py-3",
          collapsed ? "px-2" : "px-3",
        )}
      >
        <SidebarNav groups={groups} collapsed={collapsed} />
      </div>

      {canToggle && onToggle ? (
        <div
          className={cn(
            "border-t border-[var(--border-subtle)] p-2",
            collapsed && "flex justify-center",
          )}
        >
          <button
            type="button"
            onClick={onToggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn(
              "flex h-9 items-center gap-2 rounded-[var(--radius-md)] text-[13px] font-medium text-[color:var(--text-tertiary)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[color:var(--text-primary)]",
              collapsed ? "w-9 justify-center" : "w-full px-3",
            )}
          >
            {collapsed ? (
              <PanelLeftOpen size={18} />
            ) : (
              <>
                <PanelLeftClose size={18} />
                <span>Collapse</span>
              </>
            )}
          </button>
        </div>
      ) : null}
    </aside>
  );
}
