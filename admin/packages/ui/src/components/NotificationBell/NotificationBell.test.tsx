import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotificationBell, type NotificationBellItem } from "./NotificationBell";

const items: NotificationBellItem[] = [
  {
    id: "n1",
    title: "Invoice issued",
    body: "Invoice INV-2026-000123 has been issued.",
    createdAt: "2026-07-10T08:00:00Z",
    readAt: null,
  },
  {
    id: "n2",
    title: "KYC approved",
    body: "Your KYC submission was approved.",
    createdAt: "2026-07-09T08:00:00Z",
    readAt: "2026-07-09T09:00:00Z",
  },
];

describe("NotificationBell", () => {
  it("shows the unread count badge with an accessible label", () => {
    render(<NotificationBell items={items} unreadCount={1} />);
    const trigger = screen.getByLabelText("Notifications (1 unread)");
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveTextContent("1");
  });

  it("omits the count chip when nothing is unread", () => {
    render(<NotificationBell items={items} unreadCount={0} />);
    expect(screen.getByLabelText("Notifications")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("opens to show items and fires onItemClick with the id", async () => {
    const user = userEvent.setup();
    const onItemClick = vi.fn();
    render(
      <NotificationBell items={items} unreadCount={1} onItemClick={onItemClick} />,
    );
    await user.click(screen.getByLabelText("Notifications (1 unread)"));
    expect(await screen.findByText("Invoice issued")).toBeInTheDocument();
    expect(screen.getByText("KYC approved")).toBeInTheDocument();
    await user.click(screen.getByText("Invoice issued"));
    expect(onItemClick).toHaveBeenCalledWith("n1");
  });

  it("renders the empty label when there are no items", async () => {
    const user = userEvent.setup();
    render(<NotificationBell items={[]} unreadCount={0} />);
    await user.click(screen.getByLabelText("Notifications"));
    expect(
      await screen.findByText("You're all caught up"),
    ).toBeInTheDocument();
  });

  it("fires onOpenPreferences from the footer button", async () => {
    const user = userEvent.setup();
    const onOpenPreferences = vi.fn();
    render(
      <NotificationBell
        items={items}
        unreadCount={1}
        onOpenPreferences={onOpenPreferences}
      />,
    );
    await user.click(screen.getByLabelText("Notifications (1 unread)"));
    await user.click(
      await screen.findByRole("button", { name: "Notification preferences" }),
    );
    expect(onOpenPreferences).toHaveBeenCalled();
  });
});
