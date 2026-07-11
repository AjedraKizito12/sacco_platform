import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { NotificationEventAdminOut } from "@sacco/schemas";

vi.mock("@sacco/ui", async (importActual) => {
  const actual = await importActual<typeof import("@sacco/ui")>();
  return {
    ...actual,
    useTableUrlState: vi.fn().mockReturnValue({
      page: 1,
      pageSize: 25,
      sortColumn: null,
      sortDirection: "asc" as const,
      filters: {},
      density: "default" as const,
      setPage: vi.fn(),
      setPageSize: vi.fn(),
      setSort: vi.fn(),
      setFilter: vi.fn(),
      setFilters: vi.fn(),
      setDensity: vi.fn(),
      reset: vi.fn(),
    }),
  };
});

const resendEvent = vi.fn();
const refresh = vi.fn();

vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { notifications: { resendEvent } } }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/platform/notifications/events",
}));

import { EventsTable } from "../_components/EventsTable";

const ROWS: NotificationEventAdminOut[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    event_code: "invoice_overdue",
    recipient_kind: "tenant_user",
    recipient_user_id: "u1",
    recipient_email: "admin@sacco.test",
    channels: ["email", "in_app"],
    context: {},
    scheduled_at: "2026-07-10T08:00:00Z",
    status: "failed",
    created_at: "2026-07-10T08:00:00Z",
  },
  {
    id: "22222222-2222-2222-2222-222222222222",
    event_code: "password_reset",
    recipient_kind: "member",
    recipient_user_id: "u2",
    recipient_email: null,
    channels: ["in_app"],
    context: {},
    scheduled_at: "2026-07-10T09:00:00Z",
    status: "queued",
    created_at: "2026-07-10T09:00:00Z",
  },
];

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={client}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        {children}
      </TenantCurrencyProvider>
    </QueryClientProvider>
  );
}

describe("EventsTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resendEvent.mockResolvedValue({ data: ROWS[0] });
  });

  it("renders event rows with status badges and recipient", () => {
    render(<EventsTable rows={ROWS} totalRows={2} />, { wrapper });
    expect(screen.getByText("invoice_overdue")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(screen.getByText(/admin@sacco\.test/)).toBeInTheDocument();
  });

  it("resends a non-queued event after confirmation", async () => {
    const user = userEvent.setup();
    render(<EventsTable rows={ROWS} totalRows={2} />, { wrapper });
    const buttons = screen.getAllByRole("button", { name: "Resend" });
    await user.click(buttons[0] as HTMLElement);
    await user.click(
      await screen.findByRole("button", { name: "Resend notification" }),
    );
    await waitFor(() =>
      expect(resendEvent).toHaveBeenCalledWith(
        "11111111-1111-1111-1111-111111111111",
      ),
    );
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("disables resend for queued events", () => {
    render(<EventsTable rows={ROWS} totalRows={2} />, { wrapper });
    const buttons = screen.getAllByRole("button", { name: "Resend" });
    expect(buttons[1]).toBeDisabled();
  });
});
