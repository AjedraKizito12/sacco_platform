import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Bell } from "lucide-react";
import { NeedsAttention } from "../NeedsAttention";

describe("NeedsAttention", () => {
  it("renders only rows whose count is greater than zero", () => {
    render(
      <NeedsAttention
        items={[
          {
            icon: <Bell size={16} />,
            label: "Pending approvals",
            href: "/approvals",
            count: 3,
            value: "3",
          },
          {
            icon: <Bell size={16} />,
            label: "Loans in arrears",
            href: "/credit/loans",
            count: 0,
            value: "0",
          },
        ]}
      />,
    );
    expect(screen.getByText("Pending approvals")).toBeInTheDocument();
    // zero-count row is omitted
    expect(screen.queryByText("Loans in arrears")).not.toBeInTheDocument();
    // links to its destination
    expect(screen.getByRole("link", { name: /Pending approvals/ })).toHaveAttribute(
      "href",
      "/approvals",
    );
  });

  it("renders the all-clear empty state when every item is zero", () => {
    render(
      <NeedsAttention
        items={[
          {
            icon: <Bell size={16} />,
            label: "Pending approvals",
            href: "/approvals",
            count: 0,
            value: "0",
          },
        ]}
      />,
    );
    expect(screen.getByText(/All clear/i)).toBeInTheDocument();
    expect(screen.queryByText("Pending approvals")).not.toBeInTheDocument();
  });
});
