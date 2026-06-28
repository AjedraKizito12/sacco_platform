import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { cn } from "../../utils/cn";

export interface SidebarItemProps
  extends Omit<ComponentPropsWithoutRef<"a">, "children"> {
  icon: ReactNode;
  label: string;
  badge?: ReactNode;
  active?: boolean;
  /** When the sidebar is collapsed, only the icon renders. */
  collapsed?: boolean;
}

export function SidebarItem({
  icon,
  label,
  badge,
  active,
  collapsed,
  className,
  ...props
}: SidebarItemProps) {
  return (
    <a
      {...props}
      aria-current={active ? "page" : undefined}
      aria-label={collapsed ? label : undefined}
      className={cn(
        "flex h-11 items-center gap-3 rounded-[var(--radius-lg)] px-3 text-[14px] font-medium",
        "text-[color:var(--text-secondary)] transition-colors duration-150",
        "hover:bg-[var(--surface-hover)] hover:text-[color:var(--text-primary)]",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--border-focus)]",
        active &&
          "bg-[var(--nav-item-active-bg)] font-semibold text-[color:var(--nav-item-active-text)] hover:bg-[var(--nav-item-active-bg)] hover:text-[color:var(--nav-item-active-text)]",
        className,
      )}
    >
      <span
        className={cn(
          "inline-flex shrink-0 items-center transition-colors",
          active
            ? "text-[var(--nav-item-active-icon)]"
            : "text-[var(--icon-default)]",
        )}
      >
        {icon}
      </span>
      {collapsed ? null : (
        <>
          <span className="truncate">{label}</span>
          {badge ? <span className="ml-auto">{badge}</span> : null}
        </>
      )}
    </a>
  );
}
