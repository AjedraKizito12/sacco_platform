import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatCard } from "../../../app/platform/(authed)/operations/_components/StatCard";

describe("StatCard", () => {
  it("renders label, value, and sub", () => {
    render(<StatCard label="Tenants" value={<span>42</span>} sub={<span>38 active</span>} />);
    expect(screen.getByText("Tenants")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("38 active")).toBeInTheDocument();
  });

  it("renders as a link when href is set", () => {
    render(
      <StatCard
        label="Pending approvals"
        value={<span>3</span>}
        href="/platform/approvals?status=pending"
      />,
    );
    const link = screen.getByRole("link", { name: /pending approvals/i });
    expect(link).toHaveAttribute("href", "/platform/approvals?status=pending");
  });

  it("is not a link when href is omitted", () => {
    render(<StatCard label="Active impersonations" value={<span>1</span>} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
