# Portal v1 Sub-Plan 08: App Shell

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Branch:** Cut `feat/portal-v1/08-app-shell` from `main` (or rebase on top of sub-plans 01-07).

**Goal:** Ship the chrome that every authenticated screen sits inside: header (tenant indicator, command palette trigger, notification bell stub, user menu), sidebar (permission-conditional rendering), main layout, error boundaries that translate `SubscriptionPastDueError` / `SubscriptionSuspendedError` from the api-client into route redirects, and the three system pages (permission-denied, subscription-past-due, account-suspended). After this sub-plan merges, the portal looks and behaves like a real operational dashboard — the placeholder home from sub-plan 04 is replaced by the platform shell.

**Architecture:**
- **Shell components live in `@sacco/ui/src/components/Shell/`** so Storybook can render them in isolation. Each is a presentational React component that takes props (no fetching). The portal's layout passes data + handlers in.
- **Auth-protected layouts run on the server** (`app/platform/(authed)/layout.tsx` and `app/(authed)/layout.tsx`). On every render they:
  1. Read the refresh cookie via the helper from sub-plan 07
  2. Mint a fresh access token by calling the FastAPI refresh endpoint server-to-server
  3. Call `GET /platform/auth/me` or `GET /auth/me` to fetch the user
  4. Pass `initialAccessToken` and `initialUser` into `<AuthProvider>` for client hydration
  5. Render the shell (`<Header>` + `<Sidebar>` + children)
- **PermissionGuard is client-side only** (UI affordance — CLAUDE.md contract D). It hides children when the user lacks a permission. **`requirePermission()` is server-side** and throws `PermissionDeniedError` which the error boundary converts to a redirect to `/permission-denied`.
- **Subscription-gate error handling.** The api-client throws `SubscriptionPastDueError` (402) and `SubscriptionSuspendedError` (403) from middleware. The shell's error boundary catches them and redirects to `/subscription-past-due` or `/account-suspended`. Server-side fetch (in layouts) wraps the call with the same conversion.
- **Permission resolver placeholder.** Until P1.7-05 (4-tier roles) is consumable, permissions are derived from `is_superuser` / `is_admin` plus the role string when present. The `requirePermission()` helper accepts a permission name and maps it via a small `ROLE_PERMISSIONS` table; sub-plan 19 (Platform Settings) extends this when role-aware endpoints land.
- **NotificationBell ships as a stub** per index §3.O. It renders the bell icon with zero unread count, no panel, and a tooltip reading "Notifications coming soon". Phase 3 wires the real feed.

**Tech Stack:** Next.js 15 App Router (server + client components), Radix UI (DropdownMenu), Lucide React, TanStack Query, `@sacco/api-client`, `@sacco/ui`.

**Portal v1 index reference:** `docs/superpowers/plans/2026-06-02-portal-v1-index.md` §Sub-plan 08.

**Required reading:**
- `docs/sacco-design-system-v2.md` §"Layout System", §"Navigation Structure", §"Permissions UX"
- Portal v1 index §3.G (subscription-gate UX), §7.2 (app shell), §7.5–7.7 (denial + gate screens)
- Sub-plan 05's `errors.ts` (the thrown errors)
- Sub-plan 07's `server-helpers.ts` (cookies + token plumbing)

**Prerequisite:** **Sub-plans 04, 05, 07 must be merged** (or rebased onto). This sub-plan consumes UI primitives, the api-client, and the auth shell.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `admin/packages/ui/src/components/Shell/Header.tsx` | Create | Header bar with slots for tenant indicator / command palette trigger / bell / user menu |
| `admin/packages/ui/src/components/Shell/Sidebar.tsx` | Create | Vertical nav (260px wide, collapsible to 72px) |
| `admin/packages/ui/src/components/Shell/SidebarItem.tsx` | Create | Single nav item (icon + label + active state) |
| `admin/packages/ui/src/components/Shell/UserMenu.tsx` | Create | DropdownMenu with profile + sign out |
| `admin/packages/ui/src/components/Shell/TenantIndicator.tsx` | Create | Chip showing the active tenant slug + impersonation badge slot |
| `admin/packages/ui/src/components/Shell/CommandPaletteTrigger.tsx` | Create | Button with "⌘K" hint — fires a callback (no palette yet) |
| `admin/packages/ui/src/components/Shell/NotificationBellStub.tsx` | Create | Stubbed bell icon + tooltip "Notifications coming soon" |
| `admin/packages/ui/src/components/Shell/index.ts` | Create | Re-exports |
| `admin/packages/ui/src/components/Shell/*.stories.tsx` | Create | Storybook coverage for each |
| `admin/packages/ui/src/index.ts` | Modify | Re-export the Shell group |
| `admin/apps/portal/src/auth/server-helpers.ts` | Modify | Implement `getServerAccessToken` (refresh server-to-server) + `requirePermission` |
| `admin/apps/portal/src/auth/permissions.ts` | Create | `PermissionDeniedError`, `ROLE_PERMISSIONS` table, `userHasPermission()` |
| `admin/apps/portal/src/auth/PermissionGuard.tsx` | Create | Client-side UI hiding |
| `admin/apps/portal/src/auth/use-current-user.ts` | Create | `useCurrentUser()` hook (reads from store hydrated by layout) |
| `admin/apps/portal/src/components/AppErrorBoundary.tsx` | Create | Catches subscription-gate errors + redirects |
| `admin/apps/portal/src/components/AppShellHeader.tsx` | Create | Portal-specific header wrapper passing user/handlers into `<Header>` |
| `admin/apps/portal/src/components/AppShellSidebar.tsx` | Create | Portal-specific sidebar wrapper with platform/tenant nav definitions |
| `admin/apps/portal/app/platform/(authed)/layout.tsx` | Create | Platform auth-protected layout |
| `admin/apps/portal/app/(tenant-authed)/layout.tsx` | Create | Tenant auth-protected layout (route group) |
| `admin/apps/portal/app/platform/(authed)/page.tsx` | Create | Platform dashboard placeholder (sub-plan 34 ships the real one) |
| `admin/apps/portal/app/(tenant-authed)/page.tsx` | Create | Tenant dashboard placeholder (sub-plan 35) |
| `admin/apps/portal/app/permission-denied/page.tsx` | Create | Explicit denial screen |
| `admin/apps/portal/app/subscription-past-due/page.tsx` | Create | 402 screen |
| `admin/apps/portal/app/account-suspended/page.tsx` | Create | 403 from gate screen |
| `admin/apps/portal/app/page.tsx` | Modify | Move placeholder home to the new platform/(authed) route group |
| `admin/apps/portal/src/components/__tests__/*.test.tsx` | Create | RTL coverage for shell + PermissionGuard + error boundary |

---

## Task 1: Header + UserMenu + TenantIndicator + CommandPaletteTrigger + NotificationBellStub

**Files:**
- Create: `admin/packages/ui/src/components/Shell/{Header,UserMenu,TenantIndicator,CommandPaletteTrigger,NotificationBellStub,index}.tsx`
- Create: `admin/packages/ui/src/components/Shell/*.test.tsx` (smoke per component)

- [ ] **Step 1: Header (presentational, takes slots as props)**

```tsx
// admin/packages/ui/src/components/Shell/Header.tsx
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
```

- [ ] **Step 2: TenantIndicator**

```tsx
// admin/packages/ui/src/components/Shell/TenantIndicator.tsx
import { Building2 } from "lucide-react";
import { Badge } from "../Badge";
import { cn } from "../../utils/cn";

export interface TenantIndicatorProps {
  tenantName: string;
  impersonating?: boolean;
  className?: string;
}

export function TenantIndicator({
  tenantName,
  impersonating,
  className,
}: TenantIndicatorProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-[var(--radius-md)]",
        "border border-[var(--border-subtle)] bg-[var(--surface-sunken)]",
        "h-[var(--height-control-sm)] px-3 text-[13px] text-[var(--text-secondary)]",
        className,
      )}
    >
      <Building2 size={14} strokeWidth={1.75} aria-hidden />
      <span className="font-medium text-[var(--text-primary)]">{tenantName}</span>
      {impersonating ? (
        <Badge variant="warning" withDot>
          Impersonating
        </Badge>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 3: CommandPaletteTrigger (stub)**

```tsx
// admin/packages/ui/src/components/Shell/CommandPaletteTrigger.tsx
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
```

- [ ] **Step 4: NotificationBellStub**

```tsx
// admin/packages/ui/src/components/Shell/NotificationBellStub.tsx
import { Bell } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../Tooltip";

export function NotificationBellStub() {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            disabled
            aria-label="Notifications (coming soon)"
            className="inline-flex h-[var(--height-control-sm)] w-[var(--height-control-sm)] items-center justify-center rounded-[var(--radius-md)] text-[var(--icon-default)] hover:bg-[var(--surface-hover)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Bell size={18} strokeWidth={1.75} aria-hidden />
          </button>
        </TooltipTrigger>
        <TooltipContent>Notifications coming soon</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
```

- [ ] **Step 5: UserMenu (Radix DropdownMenu)**

```tsx
// admin/packages/ui/src/components/Shell/UserMenu.tsx
import { LogOut, User } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../DropdownMenu";
import { cn } from "../../utils/cn";

export interface UserMenuProps {
  fullName: string;
  email: string;
  /** Optional role/permission badge text shown under the email. */
  contextLabel?: string;
  onProfile?(): void;
  onSignOut(): void;
  className?: string;
}

function initials(fullName: string): string {
  return fullName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

export function UserMenu({
  fullName,
  email,
  contextLabel,
  onProfile,
  onSignOut,
  className,
}: UserMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`User menu for ${fullName}`}
          className={cn(
            "inline-flex h-[var(--height-control-sm)] w-[var(--height-control-sm)] items-center justify-center rounded-full",
            "bg-[var(--surface-sunken)] text-[13px] font-medium text-[var(--text-primary)]",
            "hover:bg-[var(--surface-active)]",
            "focus-visible:outline-2 focus-visible:outline-[var(--border-focus)]",
            className,
          )}
        >
          {initials(fullName)}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[220px]">
        <DropdownMenuLabel>
          <div className="text-[13px] font-medium text-[var(--text-primary)]">
            {fullName}
          </div>
          <div className="text-[12px] text-[var(--text-tertiary)]">{email}</div>
          {contextLabel ? (
            <div className="mt-1 text-[11px] font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
              {contextLabel}
            </div>
          ) : null}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {onProfile ? (
          <DropdownMenuItem onSelect={onProfile}>
            <User size={14} strokeWidth={1.75} className="mr-2" />
            Profile
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuItem onSelect={onSignOut}>
          <LogOut size={14} strokeWidth={1.75} className="mr-2" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

- [ ] **Step 6: Shell index + Vitest smoke tests**

```typescript
// admin/packages/ui/src/components/Shell/index.ts
export { Header, type HeaderProps } from "./Header";
export { Sidebar, type SidebarProps } from "./Sidebar";
export { SidebarItem, type SidebarItemProps } from "./SidebarItem";
export { UserMenu, type UserMenuProps } from "./UserMenu";
export { TenantIndicator, type TenantIndicatorProps } from "./TenantIndicator";
export {
  CommandPaletteTrigger,
  type CommandPaletteTriggerProps,
} from "./CommandPaletteTrigger";
export { NotificationBellStub } from "./NotificationBellStub";
```

Update `admin/packages/ui/src/index.ts`:

```typescript
export * from "./components/Shell";
```

Smoke test per component (one file each). Example for `Header`:

```tsx
// admin/packages/ui/src/components/Shell/Header.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Header } from "./Header";

describe("Header", () => {
  it("renders logo + provided slots", () => {
    render(
      <Header
        logo={<span>SACCO</span>}
        start={<span>Acme</span>}
        end={<span>menu</span>}
      />,
    );
    expect(screen.getByText("SACCO")).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("menu")).toBeInTheDocument();
  });
});
```

Add equivalent smoke tests for `TenantIndicator`, `CommandPaletteTrigger`, `NotificationBellStub`, `UserMenu`. Each asserts the visible label/aria-label is present.

- [ ] **Step 7: Run tests + commit**

```bash
cd admin
pnpm --filter @sacco/ui test
```

```bash
git add admin/packages/ui/src/components/Shell/{Header,UserMenu,TenantIndicator,CommandPaletteTrigger,NotificationBellStub,index}.{tsx,ts,test.tsx} \
        admin/packages/ui/src/index.ts
git commit -m "feat(ui): Header + UserMenu + TenantIndicator + CommandPaletteTrigger + NotificationBellStub"
```

---

## Task 2: Sidebar + SidebarItem

**Files:**
- Create: `admin/packages/ui/src/components/Shell/SidebarItem.tsx`
- Create: `admin/packages/ui/src/components/Shell/Sidebar.tsx`
- Create: `admin/packages/ui/src/components/Shell/Sidebar.test.tsx`

- [ ] **Step 1: SidebarItem**

```tsx
// admin/packages/ui/src/components/Shell/SidebarItem.tsx
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
```

- [ ] **Step 2: Sidebar (groups)**

```tsx
// admin/packages/ui/src/components/Shell/Sidebar.tsx
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
```

- [ ] **Step 3: Smoke test**

```tsx
// admin/packages/ui/src/components/Shell/Sidebar.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Sidebar } from "./Sidebar";
import { SidebarItem } from "./SidebarItem";
import { LayoutGrid } from "lucide-react";

describe("Sidebar", () => {
  it("renders group label + items", () => {
    render(
      <Sidebar
        groups={[
          {
            label: "Platform",
            items: (
              <SidebarItem
                href="/platform/tenants"
                icon={<LayoutGrid size={16} />}
                label="Tenants"
              />
            ),
          },
        ]}
      />,
    );
    expect(screen.getByText("Platform")).toBeInTheDocument();
    expect(screen.getByText("Tenants")).toBeInTheDocument();
    expect(screen.getByLabelText("Primary")).toBeInTheDocument();
  });

  it("hides labels when collapsed", () => {
    render(
      <Sidebar
        collapsed
        groups={[
          {
            label: "Platform",
            items: (
              <SidebarItem
                href="/platform/tenants"
                icon={<LayoutGrid size={16} />}
                label="Tenants"
                collapsed
              />
            ),
          },
        ]}
      />,
    );
    expect(screen.queryByText("Tenants")).toBeNull();
    expect(screen.getByLabelText("Tenants")).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Commit**

```bash
git add admin/packages/ui/src/components/Shell/{Sidebar,SidebarItem,Sidebar.test}.tsx
git commit -m "feat(ui): Sidebar + SidebarItem with collapsed mode"
```

---

## Task 3: Storybook stories for the shell

**Files:**
- Create: `admin/packages/ui/src/components/Shell/Header.stories.tsx`
- Create: `admin/packages/ui/src/components/Shell/Sidebar.stories.tsx`
- Create: `admin/packages/ui/src/components/Shell/TenantIndicator.stories.tsx`
- Create: `admin/packages/ui/src/components/Shell/UserMenu.stories.tsx`

- [ ] **Step 1: Header stories**

```tsx
// admin/packages/ui/src/components/Shell/Header.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { Header } from "./Header";
import { TenantIndicator } from "./TenantIndicator";
import { CommandPaletteTrigger } from "./CommandPaletteTrigger";
import { NotificationBellStub } from "./NotificationBellStub";
import { UserMenu } from "./UserMenu";

const meta: Meta<typeof Header> = {
  title: "Shell/Header",
  component: Header,
  parameters: { layout: "fullscreen" },
};
export default meta;
type Story = StoryObj<typeof Header>;

const Logo = () => (
  <span className="text-[14px] font-semibold tracking-tight">SACCO</span>
);

export const Platform: Story = {
  args: {
    logo: <Logo />,
    center: <CommandPaletteTrigger onActivate={() => {}} />,
    end: (
      <>
        <NotificationBellStub />
        <UserMenu
          fullName="Jane Operator"
          email="jane@platform.example"
          contextLabel="Superuser"
          onSignOut={() => {}}
        />
      </>
    ),
  },
};

export const TenantContext: Story = {
  args: {
    logo: <Logo />,
    start: <TenantIndicator tenantName="Sacco One" />,
    center: <CommandPaletteTrigger onActivate={() => {}} />,
    end: (
      <>
        <NotificationBellStub />
        <UserMenu
          fullName="Mary Operator"
          email="mary@sacco-one.example"
          contextLabel="Admin"
          onSignOut={() => {}}
        />
      </>
    ),
  },
};

export const Impersonating: Story = {
  args: {
    logo: <Logo />,
    start: <TenantIndicator tenantName="Sacco One" impersonating />,
    center: <CommandPaletteTrigger onActivate={() => {}} />,
    end: (
      <>
        <NotificationBellStub />
        <UserMenu
          fullName="Jane Operator"
          email="jane@platform.example"
          contextLabel="Impersonating · ends 14:35 EAT"
          onSignOut={() => {}}
        />
      </>
    ),
  },
};
```

- [ ] **Step 2: Sidebar stories (platform + tenant nav samples)**

```tsx
// admin/packages/ui/src/components/Shell/Sidebar.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import {
  Banknote,
  Building2,
  CheckCircle2,
  FileText,
  History,
  Landmark,
  LayoutGrid,
  Settings,
  Users,
} from "lucide-react";
import { Sidebar } from "./Sidebar";
import { SidebarItem } from "./SidebarItem";
import { Badge } from "../Badge";

const meta: Meta<typeof Sidebar> = {
  title: "Shell/Sidebar",
  component: Sidebar,
  parameters: { layout: "fullscreen" },
};
export default meta;
type Story = StoryObj<typeof Sidebar>;

const icon = (Icon: typeof LayoutGrid) => (
  <Icon size={18} strokeWidth={1.75} />
);

export const PlatformNav: Story = {
  args: {
    groups: [
      {
        items: (
          <SidebarItem
            href="/platform"
            icon={icon(LayoutGrid)}
            label="Dashboard"
            active
          />
        ),
      },
      {
        label: "Platform",
        items: (
          <>
            <SidebarItem href="/platform/tenants" icon={icon(Building2)} label="Tenants" />
            <SidebarItem href="/platform/users" icon={icon(Users)} label="Users" />
            <SidebarItem
              href="/platform/billing/plans"
              icon={icon(Banknote)}
              label="Billing"
            />
            <SidebarItem
              href="/platform/approvals"
              icon={icon(CheckCircle2)}
              label="Approvals"
              badge={<Badge variant="warning">3</Badge>}
            />
            <SidebarItem href="/platform/audit" icon={icon(History)} label="Audit" />
            <SidebarItem
              href="/platform/settings"
              icon={icon(Settings)}
              label="Settings"
            />
          </>
        ),
      },
    ],
  },
};

export const TenantNav: Story = {
  args: {
    groups: [
      {
        items: (
          <SidebarItem
            href="/"
            icon={icon(LayoutGrid)}
            label="Dashboard"
            active
          />
        ),
      },
      {
        label: "Operations",
        items: (
          <>
            <SidebarItem href="/members" icon={icon(Users)} label="Members" />
            <SidebarItem href="/savings" icon={icon(Landmark)} label="Savings" />
            <SidebarItem href="/credit/loans" icon={icon(Banknote)} label="Loans" />
            <SidebarItem href="/fees/types" icon={icon(FileText)} label="Fees" />
          </>
        ),
      },
      {
        label: "Reports & Audit",
        items: (
          <>
            <SidebarItem href="/reports" icon={icon(FileText)} label="Reports" />
            <SidebarItem href="/audit" icon={icon(History)} label="Audit" />
          </>
        ),
      },
    ],
  },
};

export const Collapsed: Story = {
  args: {
    collapsed: true,
    groups: [
      {
        items: (
          <>
            <SidebarItem
              href="/platform"
              icon={icon(LayoutGrid)}
              label="Dashboard"
              active
              collapsed
            />
            <SidebarItem
              href="/platform/tenants"
              icon={icon(Building2)}
              label="Tenants"
              collapsed
            />
            <SidebarItem
              href="/platform/users"
              icon={icon(Users)}
              label="Users"
              collapsed
            />
          </>
        ),
      },
    ],
  },
};
```

- [ ] **Step 3: TenantIndicator + UserMenu stories**

`TenantIndicator.stories.tsx` covers default + impersonating + long name. `UserMenu.stories.tsx` covers with profile link + without.

```tsx
// admin/packages/ui/src/components/Shell/TenantIndicator.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { TenantIndicator } from "./TenantIndicator";

const meta: Meta<typeof TenantIndicator> = {
  title: "Shell/TenantIndicator",
  component: TenantIndicator,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof TenantIndicator>;

export const Default: Story = { args: { tenantName: "Sacco One" } };
export const Impersonating: Story = {
  args: { tenantName: "Sacco Two", impersonating: true },
};
```

```tsx
// admin/packages/ui/src/components/Shell/UserMenu.stories.tsx
import type { Meta, StoryObj } from "@storybook/react";
import { UserMenu } from "./UserMenu";

const meta: Meta<typeof UserMenu> = {
  title: "Shell/UserMenu",
  component: UserMenu,
  parameters: { layout: "centered" },
};
export default meta;
type Story = StoryObj<typeof UserMenu>;

export const Default: Story = {
  args: {
    fullName: "Jane Operator",
    email: "jane@platform.example",
    contextLabel: "Superuser",
    onSignOut: () => {},
  },
};

export const WithProfile: Story = {
  args: {
    fullName: "Mary Operator",
    email: "mary@sacco-one.example",
    contextLabel: "Tenant Admin",
    onProfile: () => {},
    onSignOut: () => {},
  },
};
```

- [ ] **Step 4: Verify stories load**

```bash
cd admin
pnpm --filter @sacco/ui storybook:build
```
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add admin/packages/ui/src/components/Shell/*.stories.tsx
git commit -m "feat(ui): Shell Storybook stories (Header / Sidebar / TenantIndicator / UserMenu)"
```

---

## Task 4: Permission helpers + PermissionGuard

**Files:**
- Create: `admin/apps/portal/src/auth/permissions.ts`
- Create: `admin/apps/portal/src/auth/PermissionGuard.tsx`
- Create: `admin/apps/portal/src/auth/use-current-user.ts`

- [ ] **Step 1: Permission types + role table + helper**

```typescript
// admin/apps/portal/src/auth/permissions.ts
// Centralised permission registry. Until P1.7-05's 4-tier roles ship and
// stabilise, permissions resolve via a role table here. After 05 lands +
// stabilises, this table is the single switch — every call site stays the
// same.

export class PermissionDeniedError extends Error {
  constructor(public readonly permission: string) {
    super(`Missing permission: ${permission}`);
    this.name = "PermissionDeniedError";
  }
}

/** Subset of the PlatformUser shape the portal needs for permission checks. */
export interface CurrentUserShape {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
  /** Phase 1.7-05 column. Defaults to "support" until set. */
  role?: "superuser" | "admin" | "finance" | "support";
}

// Rank for ordered role checks.
const ROLE_RANK: Record<NonNullable<CurrentUserShape["role"]>, number> = {
  superuser: 4,
  admin: 3,
  finance: 2,
  support: 1,
};

// Each permission resolves to a minimum role. New permissions added here;
// no code change at call sites.
export const PERMISSION_MIN_ROLE: Record<string, NonNullable<CurrentUserShape["role"]>> = {
  // Platform admin
  "platform.users.read": "support",
  "platform.users.write": "superuser",
  "platform.tenants.read": "support",
  "platform.tenants.write": "admin",
  "platform.tenants.create": "superuser",
  "platform.tenants.suspend": "admin",
  // Billing
  "billing.read": "finance",
  "billing.write": "admin",
  // Approvals
  "approvals.read": "support",
  "approvals.approve": "admin",
  // Audit
  "audit.read": "admin",
  // Impersonation
  "impersonation.start": "support",
  "impersonation.revoke_other": "admin",
  // JWT keys
  "platform.security.jwt_keys.read": "superuser",
};

export function userHasPermission(
  user: CurrentUserShape | null,
  permission: string,
): boolean {
  if (!user) return false;
  // Superuser flag is an emergency back-door — they always pass.
  if (user.is_superuser) return true;
  const required = PERMISSION_MIN_ROLE[permission];
  if (!required) {
    // Unknown permission: deny by default. Adding a new permission means
    // adding it to PERMISSION_MIN_ROLE.
    return false;
  }
  const userRole = user.role ?? "support";
  return (ROLE_RANK[userRole] ?? 0) >= ROLE_RANK[required];
}

/** Server-side helper — throws PermissionDeniedError when the user fails. */
export function requirePermission(
  user: CurrentUserShape | null,
  permission: string,
): asserts user is CurrentUserShape {
  if (!userHasPermission(user, permission)) {
    throw new PermissionDeniedError(permission);
  }
}
```

- [ ] **Step 2: PermissionGuard (client-side UI hiding)**

```tsx
// admin/apps/portal/src/auth/PermissionGuard.tsx
"use client";

import type { ReactNode } from "react";
import { userHasPermission } from "./permissions";
import { useCurrentUser } from "./use-current-user";

export interface PermissionGuardProps {
  permission: string;
  fallback?: ReactNode;
  children: ReactNode;
}

/**
 * Hides children if the current user lacks the permission. UX-only:
 * CLAUDE.md contract D says the API enforces; this exists so operators
 * don't see buttons they can't click.
 */
export function PermissionGuard({
  permission,
  fallback = null,
  children,
}: PermissionGuardProps) {
  const user = useCurrentUser();
  if (!userHasPermission(user, permission)) {
    return <>{fallback}</>;
  }
  return <>{children}</>;
}
```

- [ ] **Step 3: useCurrentUser hook**

```typescript
// admin/apps/portal/src/auth/use-current-user.ts
"use client";

import { create } from "zustand";
import type { CurrentUserShape } from "./permissions";

interface UserState {
  user: CurrentUserShape | null;
  setUser(u: CurrentUserShape | null): void;
}

// Separate store from token store so user info can be hydrated independently.
export const useCurrentUserStore = create<UserState>((set) => ({
  user: null,
  setUser: (u) => set({ user: u }),
}));

export function useCurrentUser(): CurrentUserShape | null {
  return useCurrentUserStore((s) => s.user);
}
```

- [ ] **Step 4: Tests**

```typescript
// admin/apps/portal/src/auth/__tests__/permissions.test.ts
import { describe, expect, it } from "vitest";
import {
  PermissionDeniedError,
  requirePermission,
  userHasPermission,
} from "../permissions";

const superuser = {
  id: "u1",
  email: "s@test.example",
  full_name: "S",
  is_active: true,
  is_superuser: true,
};

const admin = {
  id: "u2",
  email: "a@test.example",
  full_name: "A",
  is_active: true,
  is_superuser: false,
  role: "admin" as const,
};

const support = {
  id: "u3",
  email: "t@test.example",
  full_name: "T",
  is_active: true,
  is_superuser: false,
  role: "support" as const,
};

describe("userHasPermission", () => {
  it("grants superuser everything", () => {
    expect(userHasPermission(superuser, "billing.write")).toBe(true);
    expect(userHasPermission(superuser, "platform.security.jwt_keys.read")).toBe(true);
  });

  it("respects role-min mappings", () => {
    expect(userHasPermission(admin, "billing.write")).toBe(true);
    expect(userHasPermission(admin, "platform.security.jwt_keys.read")).toBe(false);
    expect(userHasPermission(support, "platform.tenants.read")).toBe(true);
    expect(userHasPermission(support, "billing.write")).toBe(false);
  });

  it("denies unknown permissions by default", () => {
    expect(userHasPermission(admin, "fictional.permission")).toBe(false);
  });

  it("denies a null user", () => {
    expect(userHasPermission(null, "billing.read")).toBe(false);
  });
});

describe("requirePermission", () => {
  it("throws when user fails", () => {
    expect(() => requirePermission(support, "billing.write")).toThrow(
      PermissionDeniedError,
    );
  });
  it("passes when user has rank", () => {
    expect(() => requirePermission(admin, "billing.write")).not.toThrow();
  });
});
```

- [ ] **Step 5: Run + commit**

```bash
cd admin
pnpm --filter @sacco/portal test
```

```bash
git add admin/apps/portal/src/auth/{permissions.ts,PermissionGuard.tsx,use-current-user.ts,__tests__/permissions.test.ts}
git commit -m "feat(portal): permission registry + PermissionGuard + useCurrentUser"
```

---

## Task 5: Server-side access-token plumbing

**Files:**
- Modify: `admin/apps/portal/src/auth/server-helpers.ts`

- [ ] **Step 1: Implement server-side refresh + me**

Replace the stub `server-helpers.ts` from sub-plan 07 with a real implementation:

```typescript
// admin/apps/portal/src/auth/server-helpers.ts
import { cookies, headers } from "next/headers";
import {
  PLATFORM_REFRESH_COOKIE,
  TENANT_REFRESH_COOKIE,
  TENANT_SLUG_COOKIE,
} from "./cookies";
import type { CurrentUserShape } from "./permissions";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";
const HEADER_TENANT_SLUG = "x-sacco-tenant-slug";

export async function getServerTenantSlug(): Promise<string | null> {
  const h = await headers();
  const fromHeader = h.get(HEADER_TENANT_SLUG);
  if (fromHeader) return fromHeader;
  const jar = await cookies();
  return jar.get(TENANT_SLUG_COOKIE)?.value ?? null;
}

/**
 * Server-to-server refresh. Reads the appropriate refresh cookie, calls
 * the FastAPI refresh endpoint directly (no Route Handler hop), and
 * returns the new access token. Returns null when there's no cookie or
 * the backend rejects.
 *
 * This is the access-token source for server components in auth-protected
 * layouts.
 */
export async function getServerAccessToken(
  variant: "platform" | "tenant",
): Promise<{ accessToken: string | null; expiresIn: number | null }> {
  const jar = await cookies();
  const refreshCookieName =
    variant === "platform" ? PLATFORM_REFRESH_COOKIE : TENANT_REFRESH_COOKIE;
  const refreshToken = jar.get(refreshCookieName)?.value;
  if (!refreshToken) return { accessToken: null, expiresIn: null };

  const endpoint =
    variant === "platform"
      ? "/platform/auth/refresh"
      : "/auth/refresh";

  const headersInit: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (variant === "tenant") {
    const slug = await getServerTenantSlug();
    if (!slug) return { accessToken: null, expiresIn: null };
    headersInit["X-Tenant-Slug"] = slug;
  }

  const r = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: headersInit,
    body: JSON.stringify({ refresh_token: refreshToken }),
    cache: "no-store",
  });
  if (!r.ok) return { accessToken: null, expiresIn: null };
  const data = (await r.json()) as {
    access_token: string;
    expires_in: number;
  };
  return { accessToken: data.access_token, expiresIn: data.expires_in };
}

/**
 * Calls /auth/me or /platform/auth/me with the provided access token and
 * returns the user shape. Returns null on any failure.
 */
export async function getServerCurrentUser(
  variant: "platform" | "tenant",
  accessToken: string,
): Promise<CurrentUserShape | null> {
  const endpoint =
    variant === "platform" ? "/platform/auth/me" : "/auth/me";
  const headersInit: Record<string, string> = {
    Authorization: `Bearer ${accessToken}`,
  };
  if (variant === "tenant") {
    const slug = await getServerTenantSlug();
    if (slug) headersInit["X-Tenant-Slug"] = slug;
  }
  const r = await fetch(`${API_BASE}${endpoint}`, {
    headers: headersInit,
    cache: "no-store",
  });
  if (!r.ok) return null;
  return (await r.json()) as CurrentUserShape;
}
```

- [ ] **Step 2: Commit**

```bash
git add admin/apps/portal/src/auth/server-helpers.ts
git commit -m "feat(portal): server-side access-token + /me plumbing for RSC"
```

---

## Task 6: Error boundary + AuthProvider hydration upgrade

**Files:**
- Create: `admin/apps/portal/src/components/AppErrorBoundary.tsx`
- Modify: `admin/apps/portal/src/auth/AuthProvider.tsx`

- [ ] **Step 1: Error boundary (client component)**

```tsx
// admin/apps/portal/src/components/AppErrorBoundary.tsx
"use client";

import {
  SubscriptionPastDueError,
  SubscriptionSuspendedError,
  UnauthorizedError,
} from "@sacco/api-client";
import { useRouter } from "next/navigation";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { PermissionDeniedError } from "@/auth/permissions";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches the four typed errors that can bubble out of any render or
 * mutation, and routes to the matching system page. Other errors bubble
 * to Next.js's default error UI.
 */
export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Sub-plan 40 (Sentry) wires the real reporter. Until then, just log.
    console.error("AppErrorBoundary caught:", error, info);
  }

  componentDidUpdate(_: Props, prev: State): void {
    if (prev.error === this.state.error) return;
    const e = this.state.error;
    if (!e) return;
    if (e instanceof SubscriptionPastDueError) {
      window.location.assign("/subscription-past-due");
    } else if (e instanceof SubscriptionSuspendedError) {
      window.location.assign("/account-suspended");
    } else if (e instanceof PermissionDeniedError) {
      window.location.assign("/permission-denied");
    } else if (e instanceof UnauthorizedError) {
      window.location.assign("/login");
    }
  }

  render(): ReactNode {
    if (this.state.error) return null;
    return this.props.children;
  }
}

/** Hook variant for hooks-only consumers (no fall-through). */
export function useErrorRedirect(error: unknown): void {
  const router = useRouter();
  if (!error) return;
  if (error instanceof SubscriptionPastDueError) {
    router.push("/subscription-past-due");
  } else if (error instanceof SubscriptionSuspendedError) {
    router.push("/account-suspended");
  } else if (error instanceof PermissionDeniedError) {
    router.push("/permission-denied");
  } else if (error instanceof UnauthorizedError) {
    router.push("/login");
  }
}
```

- [ ] **Step 2: Upgrade AuthProvider to hydrate user**

In `admin/apps/portal/src/auth/AuthProvider.tsx`, extend `AuthProviderProps` and the hydration effect to set the current user:

```typescript
import { useCurrentUserStore } from "./use-current-user";
import type { CurrentUserShape } from "./permissions";

interface AuthProviderProps {
  children: ReactNode;
  baseUrl: string;
  initialAccessToken?: string | null;
  initialTenantSlug?: string | null;
  initialAuthContext?: "platform" | "tenant";
  initialUser?: CurrentUserShape | null;
}
```

In the `useEffect`:

```typescript
  useEffect(() => {
    const store = useAuthStore.getState();
    if (initialAccessToken !== undefined) store.setAccessToken(initialAccessToken);
    if (initialTenantSlug !== undefined) store.setTenantSlug(initialTenantSlug);
    if (initialAuthContext) store.setAuthContext(initialAuthContext);
    if (initialUser !== undefined) {
      useCurrentUserStore.getState().setUser(initialUser);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
```

- [ ] **Step 3: Commit**

```bash
git add admin/apps/portal/src/components/AppErrorBoundary.tsx \
        admin/apps/portal/src/auth/AuthProvider.tsx
git commit -m "feat(portal): AppErrorBoundary + AuthProvider user hydration"
```

---

## Task 7: Auth-protected layouts (platform + tenant)

**Files:**
- Create: `admin/apps/portal/src/components/AppShellHeader.tsx`
- Create: `admin/apps/portal/src/components/AppShellSidebar.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/layout.tsx`
- Create: `admin/apps/portal/app/platform/(authed)/page.tsx`
- Create: `admin/apps/portal/app/(tenant-authed)/layout.tsx`
- Create: `admin/apps/portal/app/(tenant-authed)/page.tsx`
- Modify: `admin/apps/portal/app/page.tsx`

- [ ] **Step 1: AppShellHeader (client wrapper)**

```tsx
// admin/apps/portal/src/components/AppShellHeader.tsx
"use client";

import {
  CommandPaletteTrigger,
  Header,
  NotificationBellStub,
  TenantIndicator,
  UserMenu,
} from "@sacco/ui";
import { useAuthStore } from "@/auth/token-store";
import { useCurrentUser } from "@/auth/use-current-user";

interface AppShellHeaderProps {
  variant: "platform" | "tenant";
  tenantName?: string;
}

function PortalLogo() {
  return (
    <span className="text-[14px] font-semibold tracking-tight text-[var(--text-primary)]">
      SACCO
    </span>
  );
}

export function AppShellHeader({ variant, tenantName }: AppShellHeaderProps) {
  const user = useCurrentUser();
  const authContext = useAuthStore((s) => s.authContext);

  async function onSignOut() {
    const endpoint =
      variant === "platform"
        ? "/api/auth/platform-logout"
        : "/api/auth/tenant-logout";
    await fetch(endpoint, {
      method: "POST",
      credentials: "include",
    }).catch(() => {});
    window.location.assign(variant === "platform" ? "/platform/login" : "/login");
  }

  return (
    <Header
      logo={<PortalLogo />}
      start={
        variant === "tenant" && tenantName ? (
          <TenantIndicator tenantName={tenantName} />
        ) : null
      }
      center={
        <CommandPaletteTrigger
          onActivate={() => {
            // Real palette ships in sub-plan 36
          }}
        />
      }
      end={
        <>
          <NotificationBellStub />
          {user ? (
            <UserMenu
              fullName={user.full_name}
              email={user.email}
              contextLabel={
                user.is_superuser
                  ? "Superuser"
                  : (user.role ?? "support").toUpperCase()
              }
              onSignOut={onSignOut}
            />
          ) : null}
        </>
      }
    />
  );
}
```

- [ ] **Step 2: AppShellSidebar (client wrapper with nav definitions)**

```tsx
// admin/apps/portal/src/components/AppShellSidebar.tsx
"use client";

import { Sidebar, SidebarItem } from "@sacco/ui";
import {
  Banknote,
  Building2,
  CheckCircle2,
  FileText,
  History,
  Landmark,
  LayoutGrid,
  PieChart,
  Settings,
  Users,
} from "lucide-react";
import { usePathname } from "next/navigation";
import { PermissionGuard } from "@/auth/PermissionGuard";

interface AppShellSidebarProps {
  variant: "platform" | "tenant";
}

const ICON_SIZE = 18;

export function AppShellSidebar({ variant }: AppShellSidebarProps) {
  const pathname = usePathname();
  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);

  if (variant === "platform") {
    return (
      <Sidebar
        groups={[
          {
            items: (
              <SidebarItem
                href="/platform"
                icon={<LayoutGrid size={ICON_SIZE} strokeWidth={1.75} />}
                label="Dashboard"
                active={pathname === "/platform"}
              />
            ),
          },
          {
            label: "Platform",
            items: (
              <>
                <PermissionGuard permission="platform.tenants.read">
                  <SidebarItem
                    href="/platform/tenants"
                    icon={<Building2 size={ICON_SIZE} strokeWidth={1.75} />}
                    label="Tenants"
                    active={isActive("/platform/tenants")}
                  />
                </PermissionGuard>
                <PermissionGuard permission="platform.users.read">
                  <SidebarItem
                    href="/platform/users"
                    icon={<Users size={ICON_SIZE} strokeWidth={1.75} />}
                    label="Users"
                    active={isActive("/platform/users")}
                  />
                </PermissionGuard>
                <PermissionGuard permission="billing.read">
                  <SidebarItem
                    href="/platform/billing/plans"
                    icon={<Banknote size={ICON_SIZE} strokeWidth={1.75} />}
                    label="Billing"
                    active={isActive("/platform/billing")}
                  />
                </PermissionGuard>
                <PermissionGuard permission="approvals.read">
                  <SidebarItem
                    href="/platform/approvals"
                    icon={<CheckCircle2 size={ICON_SIZE} strokeWidth={1.75} />}
                    label="Approvals"
                    active={isActive("/platform/approvals")}
                  />
                </PermissionGuard>
                <PermissionGuard permission="audit.read">
                  <SidebarItem
                    href="/platform/audit"
                    icon={<History size={ICON_SIZE} strokeWidth={1.75} />}
                    label="Audit"
                    active={isActive("/platform/audit")}
                  />
                </PermissionGuard>
                <SidebarItem
                  href="/platform/settings"
                  icon={<Settings size={ICON_SIZE} strokeWidth={1.75} />}
                  label="Settings"
                  active={isActive("/platform/settings")}
                />
              </>
            ),
          },
        ]}
      />
    );
  }

  // Tenant
  return (
    <Sidebar
      groups={[
        {
          items: (
            <SidebarItem
              href="/"
              icon={<LayoutGrid size={ICON_SIZE} strokeWidth={1.75} />}
              label="Dashboard"
              active={pathname === "/"}
            />
          ),
        },
        {
          label: "Operations",
          items: (
            <>
              <SidebarItem
                href="/members"
                icon={<Users size={ICON_SIZE} strokeWidth={1.75} />}
                label="Members"
                active={isActive("/members")}
              />
              <SidebarItem
                href="/savings"
                icon={<Landmark size={ICON_SIZE} strokeWidth={1.75} />}
                label="Savings"
                active={isActive("/savings")}
              />
              <SidebarItem
                href="/shares"
                icon={<PieChart size={ICON_SIZE} strokeWidth={1.75} />}
                label="Shares"
                active={isActive("/shares")}
              />
              <SidebarItem
                href="/credit/loans"
                icon={<Banknote size={ICON_SIZE} strokeWidth={1.75} />}
                label="Loans"
                active={isActive("/credit")}
              />
              <SidebarItem
                href="/fees/types"
                icon={<FileText size={ICON_SIZE} strokeWidth={1.75} />}
                label="Fees"
                active={isActive("/fees")}
              />
            </>
          ),
        },
        {
          label: "Books",
          items: (
            <>
              <SidebarItem
                href="/ledger/accounts"
                icon={<FileText size={ICON_SIZE} strokeWidth={1.75} />}
                label="Ledger"
                active={isActive("/ledger")}
              />
              <SidebarItem
                href="/reports"
                icon={<FileText size={ICON_SIZE} strokeWidth={1.75} />}
                label="Reports"
                active={isActive("/reports")}
              />
            </>
          ),
        },
        {
          label: "Approvals & Audit",
          items: (
            <>
              <SidebarItem
                href="/approvals"
                icon={<CheckCircle2 size={ICON_SIZE} strokeWidth={1.75} />}
                label="Approvals"
                active={isActive("/approvals")}
              />
              <PermissionGuard permission="audit.read">
                <SidebarItem
                  href="/audit"
                  icon={<History size={ICON_SIZE} strokeWidth={1.75} />}
                  label="Audit"
                  active={isActive("/audit")}
                />
              </PermissionGuard>
            </>
          ),
        },
      ]}
    />
  );
}
```

- [ ] **Step 3: Platform auth-protected layout**

```tsx
// admin/apps/portal/app/platform/(authed)/layout.tsx
import { redirect } from "next/navigation";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import { AppShellHeader } from "@/components/AppShellHeader";
import { AppShellSidebar } from "@/components/AppShellSidebar";
import { AuthProvider } from "@/auth/AuthProvider";
import {
  getServerAccessToken,
  getServerCurrentUser,
} from "@/auth/server-helpers";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export default async function PlatformAuthedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { accessToken } = await getServerAccessToken("platform");
  if (!accessToken) {
    redirect("/platform/login");
  }
  const user = await getServerCurrentUser("platform", accessToken);
  if (!user) {
    redirect("/platform/login");
  }
  return (
    <AuthProvider
      baseUrl={API_BASE}
      initialAccessToken={accessToken}
      initialAuthContext="platform"
      initialUser={user}
    >
      <AppErrorBoundary>
        <div className="flex min-h-screen">
          <div className="flex w-full flex-col">
            <AppShellHeader variant="platform" />
            <div className="flex flex-1">
              <AppShellSidebar variant="platform" />
              <main className="mx-auto w-full max-w-[var(--width-content-max)] p-6">
                {children}
              </main>
            </div>
          </div>
        </div>
      </AppErrorBoundary>
    </AuthProvider>
  );
}
```

- [ ] **Step 4: Tenant auth-protected layout**

The tenant layout follows the same shape with `variant="tenant"`, redirects to `/login` on failure, and pulls the tenant name from a server call. For v1 we use the slug as the tenant name; sub-plan 13 (Tenants list) lands the human name resolution.

```tsx
// admin/apps/portal/app/(tenant-authed)/layout.tsx
import { redirect } from "next/navigation";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import { AppShellHeader } from "@/components/AppShellHeader";
import { AppShellSidebar } from "@/components/AppShellSidebar";
import { AuthProvider } from "@/auth/AuthProvider";
import {
  getServerAccessToken,
  getServerCurrentUser,
  getServerTenantSlug,
} from "@/auth/server-helpers";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export default async function TenantAuthedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const slug = await getServerTenantSlug();
  if (!slug) redirect("/login");
  const { accessToken } = await getServerAccessToken("tenant");
  if (!accessToken) redirect("/login");
  const user = await getServerCurrentUser("tenant", accessToken);
  if (!user) redirect("/login");

  return (
    <AuthProvider
      baseUrl={API_BASE}
      initialAccessToken={accessToken}
      initialAuthContext="tenant"
      initialTenantSlug={slug}
      initialUser={user}
    >
      <AppErrorBoundary>
        <div className="flex min-h-screen">
          <div className="flex w-full flex-col">
            <AppShellHeader variant="tenant" tenantName={slug} />
            <div className="flex flex-1">
              <AppShellSidebar variant="tenant" />
              <main className="mx-auto w-full max-w-[var(--width-content-max)] p-6">
                {children}
              </main>
            </div>
          </div>
        </div>
      </AppErrorBoundary>
    </AuthProvider>
  );
}
```

- [ ] **Step 5: Placeholder pages**

```tsx
// admin/apps/portal/app/platform/(authed)/page.tsx
import { Card } from "@sacco/ui";

export default function PlatformDashboard() {
  return (
    <Card className="p-6">
      <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
        Platform dashboard
      </h1>
      <p className="text-[var(--text-secondary)]">
        Sub-plan 34 ships the real platform dashboard with tenant counts,
        MRR, outstanding invoices, and pending approvals via
        `GET /platform/admin/dashboard-stats`.
      </p>
    </Card>
  );
}
```

```tsx
// admin/apps/portal/app/(tenant-authed)/page.tsx
import { Card } from "@sacco/ui";

export default function TenantDashboard() {
  return (
    <Card className="p-6">
      <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
        Tenant dashboard
      </h1>
      <p className="text-[var(--text-secondary)]">
        Sub-plan 35 ships the real tenant dashboard (KPIs, charts, recent
        activity).
      </p>
    </Card>
  );
}
```

Update the existing root home (now lives under platform context):

```tsx
// admin/apps/portal/app/page.tsx
import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { PLATFORM_REFRESH_COOKIE, TENANT_REFRESH_COOKIE } from "@/auth/cookies";

export default async function Index() {
  const jar = await cookies();
  if (jar.has(PLATFORM_REFRESH_COOKIE)) redirect("/platform");
  if (jar.has(TENANT_REFRESH_COOKIE)) redirect("/");
  // No session at all — middleware would have redirected most paths but the
  // root is technically public. Send the user to the platform login as the
  // default starting point.
  redirect("/platform/login");
}
```

- [ ] **Step 6: Commit**

```bash
git add admin/apps/portal/src/components/{AppShellHeader,AppShellSidebar}.tsx \
        admin/apps/portal/app/platform/\(authed\)/ \
        admin/apps/portal/app/\(tenant-authed\)/ \
        admin/apps/portal/app/page.tsx
git commit -m "feat(portal): auth-protected layouts (platform + tenant) + shell wiring"
```

---

## Task 8: System pages — permission-denied, subscription-past-due, account-suspended

**Files:**
- Create: `admin/apps/portal/app/permission-denied/page.tsx`
- Create: `admin/apps/portal/app/subscription-past-due/page.tsx`
- Create: `admin/apps/portal/app/account-suspended/page.tsx`

- [ ] **Step 1: Permission denied**

```tsx
// admin/apps/portal/app/permission-denied/page.tsx
import { Button, Card } from "@sacco/ui";
import { Lock } from "lucide-react";
import Link from "next/link";

export default function PermissionDenied() {
  return (
    <main className="mx-auto grid min-h-screen max-w-2xl place-items-center p-8">
      <Card className="w-full p-10 text-center">
        <Lock
          size={48}
          strokeWidth={1.75}
          className="mx-auto mb-4 text-[var(--icon-default)]"
          aria-hidden
        />
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
          You don't have permission to view this section
        </h1>
        <p className="mb-6 text-[var(--text-secondary)]">
          Contact your administrator if you believe this is wrong.
        </p>
        <Button asChild>
          <Link href="/">Back to dashboard</Link>
        </Button>
      </Card>
    </main>
  );
}
```

- [ ] **Step 2: Subscription past due (402)**

```tsx
// admin/apps/portal/app/subscription-past-due/page.tsx
import { Button, Card } from "@sacco/ui";
import { AlertTriangle } from "lucide-react";
import Link from "next/link";

export default function SubscriptionPastDue() {
  return (
    <main className="mx-auto grid min-h-screen max-w-2xl place-items-center p-8">
      <Card className="w-full p-10 text-center">
        <AlertTriangle
          size={48}
          strokeWidth={1.75}
          className="mx-auto mb-4 text-[var(--text-warning)]"
          aria-hidden
        />
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
          Subscription past due — payment required
        </h1>
        <p className="mb-6 text-[var(--text-secondary)]">
          Your tenant's subscription is past due and the grace period has
          expired. Settle the outstanding invoice to restore access. Contact
          finance if you believe this is in error.
        </p>
        <div className="flex justify-center gap-3">
          <Button asChild>
            <Link href="/billing">View invoices</Link>
          </Button>
          <Button variant="secondary" asChild>
            <a href="mailto:finance@sacco.example">Contact finance</a>
          </Button>
        </div>
      </Card>
    </main>
  );
}
```

- [ ] **Step 3: Account suspended (403 from gate)**

```tsx
// admin/apps/portal/app/account-suspended/page.tsx
import { Button, Card } from "@sacco/ui";
import { Ban } from "lucide-react";

export default function AccountSuspended() {
  return (
    <main className="mx-auto grid min-h-screen max-w-2xl place-items-center p-8">
      <Card className="w-full p-10 text-center">
        <Ban
          size={48}
          strokeWidth={1.75}
          className="mx-auto mb-4 text-[var(--text-danger)]"
          aria-hidden
        />
        <h1 className="mb-2 text-[var(--text-h3)] font-semibold">
          Account suspended
        </h1>
        <p className="mb-6 text-[var(--text-secondary)]">
          Access to this tenant has been suspended. Contact the platform
          administrator to restore it.
        </p>
        <Button asChild>
          <a href="mailto:support@sacco.example">Contact platform admin</a>
        </Button>
      </Card>
    </main>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add admin/apps/portal/app/{permission-denied,subscription-past-due,account-suspended}/
git commit -m "feat(portal): permission-denied + subscription-past-due + account-suspended pages"
```

---

## Task 9: Smoke tests for the shell + error boundary

**Files:**
- Create: `admin/apps/portal/src/components/__tests__/AppErrorBoundary.test.tsx`
- Create: `admin/apps/portal/src/components/__tests__/PermissionGuard.test.tsx`

- [ ] **Step 1: AppErrorBoundary**

```tsx
// admin/apps/portal/src/components/__tests__/AppErrorBoundary.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import {
  SubscriptionPastDueError,
  SubscriptionSuspendedError,
} from "@sacco/api-client";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";

// Replace window.location.assign so we can observe the redirect target.
beforeEach(() => {
  Object.defineProperty(window, "location", {
    value: { assign: vi.fn() },
    writable: true,
  });
});

function Bomb({ throwable }: { throwable: Error }) {
  throw throwable;
}

describe("AppErrorBoundary", () => {
  it("redirects to /subscription-past-due on 402 error", () => {
    render(
      <AppErrorBoundary>
        <Bomb throwable={new SubscriptionPastDueError("expired")} />
      </AppErrorBoundary>,
    );
    expect(window.location.assign).toHaveBeenCalledWith(
      "/subscription-past-due",
    );
  });

  it("redirects to /account-suspended on gate 403", () => {
    render(
      <AppErrorBoundary>
        <Bomb throwable={new SubscriptionSuspendedError("suspended")} />
      </AppErrorBoundary>,
    );
    expect(window.location.assign).toHaveBeenCalledWith("/account-suspended");
  });
});
```

- [ ] **Step 2: PermissionGuard**

```tsx
// admin/apps/portal/src/components/__tests__/PermissionGuard.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PermissionGuard } from "@/auth/PermissionGuard";
import { useCurrentUserStore } from "@/auth/use-current-user";

describe("PermissionGuard", () => {
  it("hides children when user lacks permission", () => {
    useCurrentUserStore.getState().setUser({
      id: "u1",
      email: "t@test.example",
      full_name: "T",
      is_active: true,
      is_superuser: false,
      role: "support",
    });
    render(
      <PermissionGuard permission="billing.write">
        <button>Edit plan</button>
      </PermissionGuard>,
    );
    expect(screen.queryByText("Edit plan")).toBeNull();
  });

  it("renders children when user has rank", () => {
    useCurrentUserStore.getState().setUser({
      id: "u2",
      email: "a@test.example",
      full_name: "A",
      is_active: true,
      is_superuser: false,
      role: "admin",
    });
    render(
      <PermissionGuard permission="billing.write">
        <button>Edit plan</button>
      </PermissionGuard>,
    );
    expect(screen.getByText("Edit plan")).toBeInTheDocument();
  });

  it("renders fallback when user lacks", () => {
    useCurrentUserStore.getState().setUser({
      id: "u3",
      email: "x@test.example",
      full_name: "X",
      is_active: true,
      is_superuser: false,
      role: "support",
    });
    render(
      <PermissionGuard
        permission="billing.write"
        fallback={<span>Read-only</span>}
      >
        <button>Edit plan</button>
      </PermissionGuard>,
    );
    expect(screen.getByText("Read-only")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run + commit**

```bash
cd admin
pnpm --filter @sacco/portal test
pnpm --filter @sacco/ui test
```

```bash
git add admin/apps/portal/src/components/__tests__/
git commit -m "test(portal): AppErrorBoundary + PermissionGuard"
```

---

## Task 10: Final verification

- [ ] **Step 1: Full pipeline**

```bash
cd admin
pnpm install
pnpm typecheck
pnpm lint
pnpm test
pnpm --filter @sacco/ui storybook:build
```
Expected: all green.

- [ ] **Step 2: Manual round-trip**

```bash
make up
make migrate
make api &
make admin-dev &
sleep 8
# Browser:
#   http://localhost:3000/platform/login (sign in as admin)
#   → redirects to /platform with the real shell
#   → sidebar shows the platform nav, header shows the user menu
#   → Sign Out from the menu clears the cookie and returns to login
pkill -f "uvicorn app.main:app" || true
pkill -f "next dev" || true
```
Expected: the platform shell renders with the placeholder dashboard; the sidebar items conditionally render based on the signed-in user's role.

- [ ] **Step 3: PR**

```bash
git push -u origin feat/portal-v1/08-app-shell
gh pr create --title "feat(portal): app shell (header + sidebar + layouts + system pages)" --body "$(cat <<'EOF'
## Summary
- Shell components in `@sacco/ui/src/components/Shell/`: Header, Sidebar, SidebarItem, UserMenu, TenantIndicator, CommandPaletteTrigger, NotificationBellStub
- Storybook stories for Header (3 variants), Sidebar (platform/tenant nav, collapsed), TenantIndicator, UserMenu
- Permission registry + `PermissionGuard` + `requirePermission()` server helper (maps to role rank; superuser back-door preserved)
- Server helpers: `getServerAccessToken("platform"|"tenant")` does the refresh round-trip and returns the access token; `getServerCurrentUser` fetches `/auth/me`
- AppErrorBoundary translates `SubscriptionPastDueError` / `SubscriptionSuspendedError` / `PermissionDeniedError` / `UnauthorizedError` into route redirects
- Platform `(authed)` + tenant `(tenant-authed)` layouts: refresh server-side → fetch `/me` → hydrate AuthProvider → render shell
- System pages: `/permission-denied`, `/subscription-past-due`, `/account-suspended`
- Root `app/page.tsx` redirects based on which refresh cookie is present
- RTL coverage for AppErrorBoundary + PermissionGuard

## Out of scope
- Display primitives (`<Money>`, `<FormattedDate>` etc.) — sub-plan 09
- DataTable wrapper — sub-plan 10
- Form primitives + maker-checker dialog — sub-plan 11
- Real command palette wiring — sub-plan 36
- Real notification bell — Phase 3

## Test plan
- [ ] `pnpm --filter @sacco/ui test` (shell smoke tests)
- [ ] `pnpm --filter @sacco/portal test` (AppErrorBoundary + PermissionGuard + earlier sub-plan tests)
- [ ] `pnpm --filter @sacco/ui storybook:build` succeeds
- [ ] Manual: sign in → redirected to /platform with full shell → Sign Out works

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Acceptance criteria (sub-plan exits here)

- [ ] Header / Sidebar / SidebarItem / UserMenu / TenantIndicator / CommandPaletteTrigger / NotificationBellStub shipped under `@sacco/ui/src/components/Shell/`
- [ ] Storybook stories for Header (3 variants), Sidebar (platform / tenant / collapsed), TenantIndicator, UserMenu
- [ ] Permission registry + `PermissionGuard` + `requirePermission()` working with the role-rank table
- [ ] `getServerAccessToken` + `getServerCurrentUser` perform the refresh + /me round-trip
- [ ] `AppErrorBoundary` redirects on the four typed errors
- [ ] `app/platform/(authed)/layout.tsx` and `app/(tenant-authed)/layout.tsx` render the full shell
- [ ] Three system pages render with the documented copy + actions
- [ ] Root `/` redirects based on cookie presence
- [ ] All new tests pass
- [ ] PR opened, CI green

## Notes for the executing subagent

- **Do not** add data fetching to the shell components themselves. They are presentational. The portal-side wrappers (`AppShellHeader`, `AppShellSidebar`) are where data + handlers come in.
- **Do not** put the access token in a cookie at this point. It stays in memory. The cookie is refresh only.
- **Do not** wire the command palette here. The trigger renders and calls a callback; the real palette ships in sub-plan 36.
- **Do not** add real notification fetching. The bell is a stub per CLAUDE.md contract O.
- **Do not** soften the `PermissionGuard` to a "show greyed out" treatment. Design system §"Permissions UX" rule 2 is clear: lacking permission means hidden, not disabled.
- The `requirePermission()` helper throws `PermissionDeniedError`. The `AppErrorBoundary` catches it and redirects. If your route needs to render a custom denial UI instead of redirecting, use `PermissionGuard` with a `fallback` prop.
- Server-side `getServerAccessToken` performs a server-to-server refresh on every page render. This is wasteful but simple for v1. A future optimisation (sub-plan 41 env management) can introduce a short-lived server-side memo cache keyed on the refresh token's JTI — but the optimisation must not weaken the security guarantees.
- The `AppErrorBoundary` uses `window.location.assign` rather than `useRouter().push` because class components don't have hooks and the redirect needs to fire during `componentDidUpdate`. Functional-component consumers can use `useErrorRedirect` for the same effect.
- The role-rank table here is the SAME contract as P1.7-05's backend table. If you change one, change the other. The portal's check is UX — the backend's check is the source of truth.
- The `(tenant-authed)` route group name is intentionally distinct from `(authed)` to keep route groups disjoint when both the platform and tenant trees are mounted in the same Next.js app. Next.js groups share underlying URL paths; this prevents collisions with `app/platform/(authed)/` deeper in the tree.
- The tenant layout uses the slug as the tenant name placeholder. Sub-plan 13 (Tenants list) introduces a `useTenant()` hook that resolves the human-readable name from the api-client and passes it into `<AppShellHeader>` via context.
- The smoke test for `AppErrorBoundary` replaces `window.location` with a mock; if your jsdom environment forbids this, switch to `vi.spyOn(window.location, "assign")` after setting `writable: true` on the property descriptor.
- If `make admin-dev` fails because of a missing `@sacco/ui` export, run `make admin-install` to pick up the Shell additions to `packages/ui/src/index.ts`.
- The placeholder dashboard pages exist so the layouts render something. Real dashboards land in sub-plans 34 and 35. If you find yourself wanting to add data fetching here, stop — that's out of scope.
