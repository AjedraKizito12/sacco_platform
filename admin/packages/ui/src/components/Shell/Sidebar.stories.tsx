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
