import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DashboardHero } from "../DashboardHero";
import { StatTile, StatTileGrid } from "../StatTile";

describe("DashboardHero", () => {
  it("renders the label, value, and a link with action when href is set", () => {
    render(
      <DashboardHero label="Total savings" href="/member/savings" action="View savings">
        UGX 1,300
      </DashboardHero>,
    );
    expect(screen.getByText("Total savings")).toBeInTheDocument();
    expect(screen.getByText("UGX 1,300")).toBeInTheDocument();
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/member/savings");
    expect(screen.getByText("View savings")).toBeInTheDocument();
  });

  it("renders as a non-link when no href is provided", () => {
    render(<DashboardHero label="MRR">UGX 0</DashboardHero>);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("UGX 0")).toBeInTheDocument();
  });
});

describe("StatTile", () => {
  it("renders label, value and hint, linking when href is set", () => {
    render(
      <StatTileGrid>
        <StatTile label="Total members" icon={<span />} href="/members" hint="Across the SACCO">
          3
        </StatTile>
      </StatTileGrid>,
    );
    expect(screen.getByText("Total members")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Across the SACCO")).toBeInTheDocument();
    expect(screen.getByRole("link")).toHaveAttribute("href", "/members");
  });

  it("renders without a link when href is omitted", () => {
    render(
      <StatTile label="Members in arrears" icon={<span />}>
        0
      </StatTile>,
    );
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("Members in arrears")).toBeInTheDocument();
  });
});
