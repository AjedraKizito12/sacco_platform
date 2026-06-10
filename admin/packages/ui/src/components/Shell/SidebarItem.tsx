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
        "flex h-10 items-center gap-3 rounded-[var(--radius-md)] px-3 text-[14px] font-medium",
        "text-[var(--text-secondary)] transition-colors",
        "hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)]",
        "focus-visible:outline-2 focus-visible:outline-[var(--border-focus)]",
        active && "bg-[var(--surface-sunken)] text-[var(--text-primary)]",
        className,
      )}
    >
      <span className="inline-flex shrink-0 items-center text-[var(--icon-default)]">
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
