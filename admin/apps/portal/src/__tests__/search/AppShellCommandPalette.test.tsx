import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const platformSearch = vi.fn();
const tenantSearch = vi.fn();
const push = vi.fn();

vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { search: { platformSearch, tenantSearch } } }),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { AppShellCommandPalette } from "../../components/AppShellCommandPalette";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function Harness() {
  const [open, setOpen] = useState(true);
  return (
    <AppShellCommandPalette variant="tenant" open={open} onOpenChange={setOpen} />
  );
}

describe("AppShellCommandPalette", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    tenantSearch.mockResolvedValue({
      data: {
        hits: [
          {
            entity_type: "member",
            id: "m1",
            title: "Grace N",
            subtitle: "M-0001",
            url: "/members/m1",
            status: "active",
            status_entity: "member",
          },
        ],
        took_ms: 3,
      },
    });
  });

  it("debounced typing queries the tenant search endpoint and shows + navigates results", async () => {
    const user = userEvent.setup();
    render(<Harness />, { wrapper });
    await user.type(screen.getByRole("textbox"), "grace");
    await waitFor(() => expect(tenantSearch).toHaveBeenCalledWith("grace"));
    const hit = await screen.findByText("Grace N");
    await user.click(hit);
    expect(push).toHaveBeenCalledWith("/members/m1");
  });

  it("does not query on a blank query", async () => {
    render(<Harness />, { wrapper });
    // No typing → no search call.
    await new Promise((r) => setTimeout(r, 250));
    expect(tenantSearch).not.toHaveBeenCalled();
  });

  it("renders a hit's StatusBadge", async () => {
    const user = userEvent.setup();
    render(<Harness />, { wrapper });
    await user.type(screen.getByRole("textbox"), "grace");
    // member/active → "Active" badge.
    expect(await screen.findByText("Active")).toBeInTheDocument();
  });

  it("surfaces a nav action matching the query and navigates on select", async () => {
    const user = userEvent.setup();
    render(<Harness />, { wrapper });
    await user.type(screen.getByRole("textbox"), "savings");
    const nav = await screen.findByText("Go to Savings");
    await user.click(nav);
    expect(push).toHaveBeenCalledWith("/savings");
  });
});
