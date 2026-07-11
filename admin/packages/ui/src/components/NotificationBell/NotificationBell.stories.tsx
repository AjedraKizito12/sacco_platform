import type { Meta, StoryObj } from "@storybook/react";
import { NotificationBell, type NotificationBellItem } from "./NotificationBell";

const items: NotificationBellItem[] = [
  {
    id: "n1",
    title: "Approval requests awaiting review",
    body: "A loan approval request from Grace N. is waiting for your review.",
    createdAt: new Date(Date.now() - 5 * 60_000).toISOString(),
    readAt: null,
  },
  {
    id: "n2",
    title: "Invoice issued",
    body: "Invoice INV-2026-000123 for July has been issued.",
    createdAt: new Date(Date.now() - 3 * 3_600_000).toISOString(),
    readAt: null,
  },
  {
    id: "n3",
    title: "System announcements",
    body: "Scheduled maintenance this Saturday 02:00–04:00 EAT.",
    createdAt: new Date(Date.now() - 2 * 86_400_000).toISOString(),
    readAt: new Date(Date.now() - 86_400_000).toISOString(),
  },
];

const meta: Meta<typeof NotificationBell> = {
  title: "Shell/NotificationBell",
  component: NotificationBell,
  parameters: { layout: "centered" },
  args: {
    onOpenPreferences: () => {},
  },
};
export default meta;
type Story = StoryObj<typeof NotificationBell>;

export const Default: Story = {
  args: { items, unreadCount: 2 },
};

export const Unread: Story = {
  args: { items, unreadCount: 2 },
};

export const Empty: Story = {
  args: { items: [], unreadCount: 0 },
};

export const Loading: Story = {
  args: { items: [], unreadCount: 0, loading: true },
};
