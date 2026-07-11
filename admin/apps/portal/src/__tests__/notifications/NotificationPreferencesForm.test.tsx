import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { catalogForAudience } from "@sacco/schemas";

const putPreferences = vi.fn();

vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { notifications: { putPreferences } } }),
}));

import { NotificationPreferencesForm } from "../../components/notifications/NotificationPreferencesForm";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("NotificationPreferencesForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    putPreferences.mockResolvedValue({ data: [] });
  });

  it("renders only the member catalog codes for the member audience", () => {
    render(<NotificationPreferencesForm audience="member" initial={[]} />, {
      wrapper,
    });
    const memberCodes = catalogForAudience("member").map((row) => row.label);
    for (const label of memberCodes) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.queryByText("Invoice issued")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Approval requests awaiting review"),
    ).not.toBeInTheDocument();
  });

  it("renders a stored enabled=false row unchecked; untouched rows default checked", () => {
    render(
      <NotificationPreferencesForm
        audience="member"
        initial={[
          { event_code: "member_activated", channel: "email", enabled: false },
        ]}
      />,
      { wrapper },
    );
    expect(
      screen.getByRole("checkbox", { name: "Membership activated via Email" }),
    ).not.toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "Membership activated via In-app" }),
    ).toBeChecked();
  });

  it("PUTs the full rendered matrix with the toggled row disabled", async () => {
    const user = userEvent.setup();
    render(<NotificationPreferencesForm audience="member" initial={[]} />, {
      wrapper,
    });
    await user.click(
      screen.getByRole("checkbox", { name: "KYC approved via Email" }),
    );
    await user.click(screen.getByRole("button", { name: "Save preferences" }));
    await waitFor(() => expect(putPreferences).toHaveBeenCalled());
    const [audience, matrix] = putPreferences.mock.calls[0] as [
      string,
      { event_code: string; channel: string; enabled: boolean }[],
    ];
    expect(audience).toBe("member");
    const memberRowCount = catalogForAudience("member").reduce(
      (n, row) => n + row.channels.length,
      0,
    );
    expect(matrix).toHaveLength(memberRowCount);
    expect(matrix).toContainEqual({
      event_code: "kyc_submission_approved",
      channel: "email",
      enabled: false,
    });
    expect(matrix).toContainEqual({
      event_code: "kyc_submission_approved",
      channel: "in_app",
      enabled: true,
    });
    expect(
      matrix.filter((row) => !row.enabled).map((row) => row.event_code),
    ).toEqual(["kyc_submission_approved"]);
  });
});
