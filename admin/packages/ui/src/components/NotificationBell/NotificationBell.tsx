"use client";

import { Bell } from "lucide-react";
import { RelativeTime } from "../FormattedDate";
import { Popover, PopoverContent, PopoverTrigger } from "../Popover";
import { Separator } from "../Separator";
import { cn } from "../../utils/cn";

export interface NotificationBellItem {
  id: string;
  title: string;
  body: string;
  createdAt: string;
  readAt: string | null;
}

export interface NotificationBellProps {
  items: NotificationBellItem[];
  unreadCount: number;
  loading?: boolean;
  /** Consumer marks the item read (and refetches). */
  onItemClick?: (id: string) => void;
  onOpenPreferences?: () => void;
  emptyLabel?: string;
}

export function NotificationBell({
  items,
  unreadCount,
  loading = false,
  onItemClick,
  onOpenPreferences,
  emptyLabel = "You're all caught up",
}: NotificationBellProps) {
  const ariaLabel =
    unreadCount > 0 ? `Notifications (${unreadCount} unread)` : "Notifications";

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={ariaLabel}
          className="relative inline-flex h-[var(--height-control-sm)] w-[var(--height-control-sm)] items-center justify-center rounded-[var(--radius-md)] text-[var(--icon-default)] hover:bg-[var(--surface-hover)]"
        >
          <Bell size={18} strokeWidth={1.75} aria-hidden />
          {unreadCount > 0 ? (
            <span
              aria-hidden
              className="absolute -right-0.5 -top-0.5 inline-flex min-w-4 items-center justify-center rounded-full bg-[var(--status-danger-solid-bg)] px-1 text-[10px] font-semibold leading-4 text-[var(--status-danger-solid-text)] [font-feature-settings:'tnum'_1]"
            >
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          ) : null}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-0">
        <div className="px-4 py-3 text-sm font-semibold text-[var(--text-primary)]">
          Notifications
        </div>
        <Separator />
        <div className="max-h-96 overflow-y-auto">
          {loading ? (
            <div className="px-4 py-6 text-sm text-[var(--text-secondary)]">
              Loading notifications…
            </div>
          ) : items.length === 0 ? (
            <div className="px-4 py-6 text-sm text-[var(--text-secondary)]">
              {emptyLabel}
            </div>
          ) : (
            <ul className="divide-y divide-[var(--border-subtle)]">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => onItemClick?.(item.id)}
                    className="block w-full px-4 py-3 text-left hover:bg-[var(--surface-hover)]"
                  >
                    <span
                      className={cn(
                        "block text-sm text-[var(--text-primary)]",
                        item.readAt === null && "font-semibold",
                      )}
                    >
                      {item.title}
                    </span>
                    <span className="mt-0.5 line-clamp-2 block text-sm text-[var(--text-secondary)]">
                      {item.body}
                    </span>
                    <RelativeTime
                      value={item.createdAt}
                      className="mt-1 block text-xs text-[var(--text-tertiary)]"
                    />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        {onOpenPreferences ? (
          <>
            <Separator />
            <button
              type="button"
              onClick={onOpenPreferences}
              className="block w-full rounded-b-[var(--radius-lg)] px-4 py-3 text-left text-sm font-medium text-[var(--text-link)] hover:bg-[var(--surface-hover)]"
            >
              Notification preferences
            </button>
          </>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
