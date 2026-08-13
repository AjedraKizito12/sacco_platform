"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";
import { cn } from "@sacco/ui";
import { PermissionGuard } from "@/auth/PermissionGuard";
import type { NavGroup, NavItem, NavLeaf } from "./nav-config";

const ICON = 18;
// Roots whose href is a prefix of their siblings — match exactly so the
// dashboard isn't "active" on every child page.
const EXACT_ROOTS = new Set(["/", "/platform", "/member/dashboard"]);

function useIsActive() {
  const pathname = usePathname();
  return (href: string) => {
    if (EXACT_ROOTS.has(href)) return pathname === href;
    return pathname === href || pathname.startsWith(`${href}/`);
  };
}

const rowBase =
  "flex h-11 w-full items-center gap-3 rounded-[var(--radius-lg)] px-3 text-[14px] font-medium text-[color:var(--text-secondary)] transition-colors duration-150 hover:bg-[var(--surface-hover)] hover:text-[color:var(--text-primary)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--border-focus)]";
const rowActive =
  "bg-[var(--nav-item-active-bg)] font-semibold text-[color:var(--nav-item-active-text)] hover:bg-[var(--nav-item-active-bg)] hover:text-[color:var(--nav-item-active-text)]";

function Leaf({
  item,
  collapsed,
  active,
}: {
  item: NavItem;
  collapsed: boolean;
  active: boolean;
}) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href ?? "#"}
      aria-current={active ? "page" : undefined}
      aria-label={collapsed ? item.label : undefined}
      title={collapsed ? item.label : undefined}
      className={cn(rowBase, collapsed && "justify-center px-0", active && rowActive)}
    >
      <span
        className={cn(
          "inline-flex shrink-0 items-center",
          active ? "text-[var(--nav-item-active-icon)]" : "text-[var(--icon-default)]",
        )}
      >
        <Icon size={ICON} strokeWidth={1.75} />
      </span>
      {collapsed ? null : <span className="truncate">{item.label}</span>}
    </Link>
  );
}

function DisabledLeaf({
  item,
  collapsed,
}: {
  item: NavItem;
  collapsed: boolean;
}) {
  const Icon = item.icon;
  return (
    <div
      aria-disabled="true"
      title={collapsed ? `${item.label} (coming soon)` : "Coming soon"}
      className={cn(
        rowBase,
        "cursor-not-allowed opacity-55 hover:bg-transparent hover:text-[color:var(--text-secondary)]",
        collapsed && "justify-center px-0",
      )}
    >
      <span className="inline-flex shrink-0 items-center text-[var(--icon-default)]">
        <Icon size={ICON} strokeWidth={1.75} />
      </span>
      {collapsed ? null : (
        <>
          <span className="truncate">{item.label}</span>
          <span className="ml-auto shrink-0 rounded-full bg-[var(--surface-hover)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[color:var(--text-tertiary)]">
            Soon
          </span>
        </>
      )}
    </div>
  );
}

function Parent({
  item,
  collapsed,
  isActive,
}: {
  item: NavItem;
  collapsed: boolean;
  isActive: (href: string) => boolean;
}) {
  const children = item.children ?? [];
  const childActive = children.some((c) => isActive(c.href));
  const ownActive = item.href ? isActive(item.href) : false;
  const containsActive = childActive || ownActive;
  const [open, setOpen] = useState<boolean | null>(null);
  const expanded = open ?? containsActive;
  const Icon = item.icon;

  // Collapsed rail: render as a single icon link to the overview / first child.
  if (collapsed) {
    const target = item.href ?? children[0]?.href ?? "#";
    return (
      <Leaf
        item={{ ...item, href: target }}
        collapsed
        active={containsActive}
      />
    );
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen(!expanded)}
        aria-expanded={expanded}
        className={cn(
          rowBase,
          containsActive && !childActive && "text-[color:var(--text-primary)]",
          ownActive && rowActive,
        )}
      >
        <span
          className={cn(
            "inline-flex shrink-0 items-center",
            containsActive ? "text-[var(--nav-item-active-icon)]" : "text-[var(--icon-default)]",
          )}
        >
          <Icon size={ICON} strokeWidth={1.75} />
        </span>
        <span className="truncate">{item.label}</span>
        <ChevronRight
          size={16}
          className={cn(
            "ml-auto shrink-0 text-[var(--icon-default)] transition-transform duration-150",
            expanded && "rotate-90",
          )}
        />
      </button>
      {expanded ? (
        <div className="mt-0.5 flex flex-col gap-0.5 pl-4">
          {children.map((child: NavLeaf) => {
            const active = isActive(child.href);
            return (
              <Link
                key={child.href}
                href={child.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-9 items-center border-l border-[var(--border-subtle)] pl-4 text-[13px] font-medium text-[color:var(--text-tertiary)] transition-colors hover:text-[color:var(--text-primary)]",
                  active &&
                    "border-[var(--color-brand-400)] font-semibold text-[color:var(--nav-item-active-text)]",
                )}
              >
                {child.label}
              </Link>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function Item({
  item,
  collapsed,
  isActive,
}: {
  item: NavItem;
  collapsed: boolean;
  isActive: (href: string) => boolean;
}) {
  const node = item.comingSoon ? (
    <DisabledLeaf item={item} collapsed={collapsed} />
  ) : item.children && item.children.length > 0 ? (
    <Parent item={item} collapsed={collapsed} isActive={isActive} />
  ) : (
    <Leaf item={item} collapsed={collapsed} active={item.href ? isActive(item.href) : false} />
  );
  return item.permission ? (
    <PermissionGuard permission={item.permission}>{node}</PermissionGuard>
  ) : (
    node
  );
}

export function SidebarNav({
  groups,
  collapsed = false,
}: {
  groups: NavGroup[];
  collapsed?: boolean;
}) {
  const isActive = useIsActive();
  return (
    <nav className="flex flex-col gap-1" aria-label="Primary">
      {groups.map((group, idx) => (
        <div
          key={group.label ?? `g${idx}`}
          className={cn("flex flex-col gap-0.5", idx > 0 && "mt-3")}
        >
          {!collapsed && group.label ? (
            <p className="mb-1 px-3 text-[11px] font-semibold uppercase tracking-wider text-[color:var(--text-tertiary)]">
              {group.label}
            </p>
          ) : null}
          {group.items.map((item) => (
            <Item
              key={item.label}
              item={item}
              collapsed={collapsed}
              isActive={isActive}
            />
          ))}
        </div>
      ))}
    </nav>
  );
}
