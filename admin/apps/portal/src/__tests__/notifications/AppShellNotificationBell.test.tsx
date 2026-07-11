import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const feed = vi.fn();
const markRead = vi.fn();
const push = vi.fn();

vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { notifications: { feed, markRead } } }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
}));

import { AppShellNotificationBell } from "../../components/AppShellNotificationBell";

const feedRows = [
  {
    id: "n1",
    event_code: "invoice_issued",
    title: "Invoice issued",
    body: "Invoice INV-2026-000123 has been issued.",
    status: "sent",
    created_at: "2026-07-10T08:00:00Z",
    read_at: null,
  },
  {
    id: "n2",
    event_code: "system_announcement",
    title: "Maintenance window",
    body: "Scheduled maintenance Saturday.",
    status: "sent",
    created_at: "2026-07-09T08:00:00Z",
    read_at: "2026-07-09T09:00:00Z",
  },
];

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("AppShellNotificationBell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    feed.mockResolvedValue({ data: feedRows });
    markRead.mockResolvedValue({ data: null });
  });

  it("renders the unread count from the fetched feed", async () => {
    render(<AppShellNotificationBell variant="tenant" />, { wrapper });
    expect(
      await screen.findByLabelText("Notifications (1 unread)"),
    ).toBeInTheDocument();
    expect(feed).toHaveBeenCalledWith("tenant", { limit: 20 });
  });

  it("marks an unread item read with the audience + id", async () => {
    const user = userEvent.setup();
    render(<AppShellNotificationBell variant="member" />, { wrapper });
    await user.click(await screen.findByLabelText("Notifications (1 unread)"));
    await user.click(await screen.findByText("Invoice issued"));
    expect(markRead).toHaveBeenCalledWith("member", "n1");
  });

  it("routes to the audience's preferences page", async () => {
    const user = userEvent.setup();
    render(<AppShellNotificationBell variant="platform" />, { wrapper });
    await user.click(await screen.findByLabelText("Notifications (1 unread)"));
    await user.click(
      await screen.findByRole("button", { name: "Notification preferences" }),
    );
    expect(push).toHaveBeenCalledWith("/platform/settings/notifications");
  });
});
