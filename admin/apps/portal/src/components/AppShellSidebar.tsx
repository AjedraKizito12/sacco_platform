"use client";

import { Sidebar, SidebarItem } from "@sacco/ui";
import {
  Activity,
  Banknote,
  Building2,
  CheckCircle2,
  FileText,
  History,
  Landmark,
  LayoutGrid,
  PieChart,
  Receipt,
  Settings,
  User,
  Users,
} from "lucide-react";
import { usePathname } from "next/navigation";
import { PermissionGuard } from "@/auth/PermissionGuard";

interface AppShellSidebarProps {
  variant: "platform" | "tenant" | "member";
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
                <PermissionGuard permission="operations.read">
                  <SidebarItem
                    href="/platform/operations"
                    icon={<Activity size={ICON_SIZE} strokeWidth={1.75} />}
                    label="Operations"
                    active={isActive("/platform/operations")}
                  />
                </PermissionGuard>
                <PermissionGuard permission="settings.read">
                  <SidebarItem
                    href="/platform/settings"
                    icon={<Settings size={ICON_SIZE} strokeWidth={1.75} />}
                    label="Settings"
                    active={isActive("/platform/settings")}
                  />
                </PermissionGuard>
              </>
            ),
          },
        ]}
      />
    );
  }

  if (variant === "member") {
    return (
      <Sidebar
        groups={[
          {
            items: (
              <SidebarItem
                href="/member/dashboard"
                icon={<LayoutGrid size={ICON_SIZE} strokeWidth={1.75} />}
                label="Dashboard"
                active={pathname === "/member/dashboard"}
              />
            ),
          },
          {
            items: (
              <>
                <SidebarItem
                  href="/member/savings"
                  icon={<Landmark size={ICON_SIZE} strokeWidth={1.75} />}
                  label="Savings"
                  active={isActive("/member/savings")}
                />
                <SidebarItem
                  href="/member/shares"
                  icon={<PieChart size={ICON_SIZE} strokeWidth={1.75} />}
                  label="Shares"
                  active={isActive("/member/shares")}
                />
                <SidebarItem
                  href="/member/loans"
                  icon={<Banknote size={ICON_SIZE} strokeWidth={1.75} />}
                  label="Loans"
                  active={isActive("/member/loans")}
                />
                <SidebarItem
                  href="/member/fees"
                  icon={<Receipt size={ICON_SIZE} strokeWidth={1.75} />}
                  label="Fees"
                  active={isActive("/member/fees")}
                />
                <SidebarItem
                  href="/member/profile"
                  icon={<User size={ICON_SIZE} strokeWidth={1.75} />}
                  label="Profile"
                  active={isActive("/member/profile")}
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
                href="/credit"
                icon={<Banknote size={ICON_SIZE} strokeWidth={1.75} />}
                label="Credit"
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
          label: "Billing",
          items: (
            <SidebarItem
              href="/billing"
              icon={<Banknote size={ICON_SIZE} strokeWidth={1.75} />}
              label="Billing"
              active={isActive("/billing")}
            />
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
              <SidebarItem
                href="/audit"
                icon={<History size={ICON_SIZE} strokeWidth={1.75} />}
                label="Audit"
                active={isActive("/audit")}
              />
            </>
          ),
        },
      ]}
    />
  );
}
