import type { ComponentType } from "react";
import {
  Activity,
  Banknote,
  Building2,
  CheckCircle2,
  FileText,
  History,
  Landmark,
  LayoutGrid,
  ListChecks,
  PieChart,
  Receipt,
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
        label: "Billing",
        icon: Banknote,
        permission: "billing.read",
        children: [
          { label: "Plans", href: "/platform/billing/plans" },
          { label: "Subscriptions", href: "/platform/billing/subscriptions" },
          { label: "Invoices", href: "/platform/billing/invoices" },
          { label: "Payments", href: "/platform/billing/payments" },
        ],
      },
      {
        label: "Approvals",
        href: "/platform/approvals",
        icon: CheckCircle2,
        permission: "approvals.read",
      },
      {
        label: "Audit",
        href: "/platform/audit",
        icon: History,
        permission: "audit.read",
      },
      {
        label: "Operations",
        href: "/platform/operations",
        icon: Activity,
        permission: "operations.read",
      },
      {
        label: "Settings",
        href: "/platform/settings",
        icon: Settings,
        permission: "settings.read",
        children: [
          { label: "Billing", href: "/platform/settings/billing" },
          { label: "Notifications", href: "/platform/settings/notifications" },
          {
            label: "Notification templates",
            href: "/platform/notifications/templates",
          },
          {
            label: "Notification events",
            href: "/platform/notifications/events",
          },
          { label: "SACCO KYC", href: "/platform/settings/kyc" },
          { label: "Security", href: "/platform/settings/security" },
        ],
      },
    ],
  },
];

export function navForVariant(variant: ShellVariant): NavGroup[] {
  if (variant === "platform") return PLATFORM_NAV;
  if (variant === "member") return MEMBER_NAV;
  return TENANT_NAV;
}
