import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Users, Banknote } from "lucide-react";
import { QuickLinks } from "../QuickLinks";

describe("QuickLinks", () => {
  it("renders a labelled link per item pointing at its href", () => {
    render(
      <QuickLinks
        items={[
          {
            icon: <Users size={18} />,
            label: "Members",
            description: "Directory & KYC",
            href: "/members",
          },
          {
            icon: <Banknote size={18} />,
            label: "Loans",
            description: "Portfolio",
            href: "/credit/loans",
          },
        ]}
      />,
    );
    expect(screen.getByRole("link", { name: /Members/ })).toHaveAttribute(
      "href",
      "/members",
    );
    expect(screen.getByRole("link", { name: /Loans/ })).toHaveAttribute(
      "href",
      "/credit/loans",
    );
    expect(screen.getByText("Directory & KYC")).toBeInTheDocument();
  });
});
