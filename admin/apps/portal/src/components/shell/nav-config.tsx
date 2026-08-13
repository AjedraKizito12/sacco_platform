import type { ComponentType } from "react";
import {
  Activity,
  BadgeCheck,
  Banknote,
  Bell,
  Building2,
  CheckCircle2,
  Clock,
  CreditCard,
  FileText,
  Gauge,
  HardDrive,
  History,
  KeyRound,
  Landmark,
  Layers,
  LayoutGrid,
  ListChecks,
  Palette,
  PieChart,
  Receipt,
  Repeat,
  ScrollText,
  Settings,
  ShieldCheck,
  User,
  Users,
  Wallet,
} from "lucide-react";

export type NavIcon = ComponentType<{ size?: number; strokeWidth?: number }>;

export interface NavLeaf {
  label: string;
  href: string;
}

export interface NavItem {
  label: string;
  icon: NavIcon;
  /** Link target. Required for leaf items; for parents it's the overview page. */
  href?: string;
  /** Expandable sub-items. */
  children?: NavLeaf[];
  /** UX-only permission gate (API still enforces). */
  permission?: string;
  /** Placeholder for a not-yet-built feature: shown disabled with a "Soon" pill. */
  comingSoon?: boolean;
}

export interface NavGroup {
  label?: string;
  items: NavItem[];
}

export type ShellVariant = "platform" | "tenant" | "member";

const MEMBER_NAV: NavGroup[] = [
  { items: [{ label: "Dashboard", href: "/member/dashboard", icon: LayoutGrid }] },
  {
    items: [
      { label: "Savings", href: "/member/savings", icon: Landmark },
      { label: "Shares", href: "/member/shares", icon: PieChart },
      { label: "Loans", href: "/member/loans", icon: Banknote },
      { label: "Fees", href: "/member/fees", icon: Receipt },
      { label: "Statements", href: "/member/statements", icon: FileText },
      { label: "Profile", href: "/member/profile", icon: User },
    ],
  },
];

const TENANT_NAV: NavGroup[] = [
  { items: [{ label: "Dashboard", href: "/", icon: LayoutGrid }] },
  {
    label: "Operations",
    items: [
      {
        label: "Members",
        href: "/members",
        icon: Users,
        children: [{ label: "KYC submissions", href: "/members/kyc-submissions" }],
      },
      {
        label: "Savings",
        href: "/savings",
        icon: Landmark,
        children: [{ label: "Accounts", href: "/savings/accounts" }],
      },
      {
        label: "Shares",
        href: "/shares",
        icon: PieChart,
        children: [{ label: "Accounts", href: "/shares/accounts" }],
      },
      {
        label: "Credit",
        href: "/credit",
        icon: Banknote,
        children: [
          { label: "Applications", href: "/credit/applications" },
          { label: "Loans", href: "/credit/loans" },
        ],
      },
      {
        label: "Fees",
        icon: Receipt,
        children: [
          { label: "Fee types", href: "/fees/types" },
          { label: "Assessments", href: "/fees/assessments" },
        ],
      },
    ],
  },
  {
    label: "Books",
    items: [
      {
        label: "Ledger",
        icon: FileText,
        children: [
          { label: "Accounts", href: "/ledger/accounts" },
          { label: "Journal entries", href: "/ledger/journal-entries" },
        ],
      },
      {
        label: "Reports",
        href: "/reports",
        icon: PieChart,
        children: [
          { label: "Trial balance", href: "/reports/trial-balance" },
          { label: "Loan portfolio", href: "/reports/loan-portfolio" },
          { label: "Income statement", href: "/reports/income-statement" },
          { label: "Savings statement", href: "/reports/savings-statement" },
          { label: "Fee collection", href: "/reports/fee-collection" },
          { label: "Report runs", href: "/reports/runs" },
        ],
      },
    ],
  },
  { label: "Billing", items: [{ label: "Billing", href: "/billing", icon: Wallet }] },
  {
    label: "Organization",
    items: [
      { label: "Organization KYC", href: "/organization/kyc", icon: ShieldCheck },
      {
        label: "Member KYC requirements",
        href: "/organization/member-kyc-requirements",
        icon: ListChecks,
      },
    ],
  },
  {
    label: "Approvals & Audit",
    items: [
      { label: "Approvals", href: "/approvals", icon: CheckCircle2 },
      { label: "Audit", href: "/audit", icon: History },
    ],
  },
  {
    label: "Settings",
    items: [{ label: "Appearance", href: "/settings/appearance", icon: Settings }],
  },
];

const PLATFORM_NAV: NavGroup[] = [
  { items: [{ label: "Dashboard", href: "/platform", icon: LayoutGrid }] },
  {
    label: "Platform",
    items: [
      {
        label: "Tenants",
        href: "/platform/tenants",
        icon: Building2,
        permission: "platform.tenants.read",
      },
      {
        label: "Users",
        href: "/platform/users",
        icon: Users,
        permission: "platform.users.read",
      },
      {
        label: "Roles & Permissions",
        icon: KeyRound,
        permission: "platform.users.read",
        comingSoon: true,
      },
    ],
  },
  {
    label: "Finance",
    items: [
      { label: "Plans", href: "/platform/billing/plans", icon: Layers, permission: "billing.read" },
      {
        label: "Subscriptions",
        href: "/platform/billing/subscriptions",
        icon: Repeat,
        permission: "billing.read",
      },
      { label: "Invoices", href: "/platform/billing/invoices", icon: Receipt, permission: "billing.read" },
      {
        label: "Payments",
        href: "/platform/billing/payments",
        icon: CreditCard,
        permission: "billing.read",
      },
    ],
  },
  {
    label: "Operations",
    items: [
      {
        label: "Approvals",
        href: "/platform/approvals",
        icon: CheckCircle2,
        permission: "approvals.read",
      },
      {
        label: "Backups",
        href: "/platform/operations/backups",
        icon: HardDrive,
        permission: "operations.read",
      },
      {
        label: "Scheduled Jobs",
        icon: Clock,
        permission: "operations.read",
        comingSoon: true,
      },
    ],
  },
  {
    label: "Monitoring",
    items: [
      { label: "Audit Logs", href: "/platform/audit", icon: History, permission: "audit.read" },
      {
        label: "System Health",
        icon: Activity,
        permission: "operations.read",
        comingSoon: true,
      },
      {
        label: "Activity Log",
        icon: ScrollText,
        permission: "audit.read",
        comingSoon: true,
      },
      {
        label: "Rate limits",
        href: "/platform/settings/rate-limits",
        icon: Gauge,
        permission: "settings.read",
      },
    ],
  },
  {
    label: "Settings",
    items: [
      {
        label: "Security",
        href: "/platform/settings/security",
        icon: ShieldCheck,
        permission: "settings.read",
      },
      {
        label: "Notifications",
        icon: Bell,
        permission: "settings.read",
        children: [
          { label: "Preferences", href: "/platform/settings/notifications" },
          { label: "Templates", href: "/platform/notifications/templates" },
          { label: "Events", href: "/platform/notifications/events" },
        ],
      },
      {
        label: "KYC Configuration",
        href: "/platform/settings/kyc",
        icon: BadgeCheck,
        permission: "settings.read",
      },
      {
        label: "Billing Configuration",
        href: "/platform/settings/billing",
        icon: Wallet,
        permission: "settings.read",
      },
      {
        label: "Appearance",
        href: "/platform/settings/appearance",
        icon: Palette,
        permission: "settings.read",
      },
    ],
  },
];

export function navForVariant(variant: ShellVariant): NavGroup[] {
  if (variant === "platform") return PLATFORM_NAV;
  if (variant === "member") return MEMBER_NAV;
  return TENANT_NAV;
}
