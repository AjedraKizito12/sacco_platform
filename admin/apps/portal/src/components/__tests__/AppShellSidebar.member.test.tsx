import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
vi.mock("next/navigation", () => ({ usePathname: () => "/member/dashboard" }));

import { AppShellSidebar } from "../AppShellSidebar";

describe("AppShellSidebar (member)", () => {
  it("renders member nav links", () => {
    render(<AppShellSidebar variant="member" />);
    for (const label of [
      "Dashboard",
      "Savings",
      "Shares",
      "Loans",
      "Fees",
      "Profile",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    // member nav never exposes operator destinations
    expect(screen.queryByText("Approvals")).not.toBeInTheDocument();
    expect(screen.queryByText("Audit")).not.toBeInTheDocument();
  });
});
