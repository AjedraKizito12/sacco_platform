import type { ReactNode } from "react";
import { cn } from "../../utils/cn";

export interface HeaderProps {
  /** Logo or wordmark on the left. */
  logo: ReactNode;
  /** Tenant indicator + breadcrumbs. */
  start?: ReactNode;
  /** Center area — usually the command palette trigger. */
  center?: ReactNode;
  /** Right-side actions: notifications, user menu. */
  end?: ReactNode;
  className?: string;
}

export function Header({ logo, start, center, end, className }: HeaderProps) {
  return (
    <header
      className={cn(
        "sticky top-0 z-[var(--z-sticky)] flex h-[var(--height-header)] items-center gap-4 px-6",
        "border-b border-[var(--border-subtle)] bg-[var(--surface-elevated)]",
        className,
      )}
    >
      <div className="flex items-center gap-3">{logo}</div>
      {start ? <div className="flex items-center gap-2">{start}</div> : null}
      <div className="flex-1" />
      {center ? <div className="flex items-center justify-center">{center}</div> : null}
      <div className="flex-1" />
      <div className="flex items-center gap-2">{end}</div>
    </header>
  );
}
