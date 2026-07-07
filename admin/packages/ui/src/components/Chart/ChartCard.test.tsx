import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChartCard } from "./ChartCard";

describe("ChartCard", () => {
  it("renders the title, subtitle and children", () => {
    render(
      <ChartCard title="Savings growth" subtitle="Last 6 months">
        <div>chart-body</div>
      </ChartCard>,
    );
    expect(screen.getByText("Savings growth")).toBeInTheDocument();
    expect(screen.getByText("Last 6 months")).toBeInTheDocument();
    expect(screen.getByText("chart-body")).toBeInTheDocument();
  });

  it("renders a See all link when seeAllHref is provided", () => {
    render(
      <ChartCard title="Loan mix" seeAllHref="/credit/loans">
        <div />
      </ChartCard>,
    );
    expect(screen.getByRole("link", { name: /See all/i })).toHaveAttribute(
      "href",
      "/credit/loans",
    );
  });

  it("omits the See all link when no href is given", () => {
    render(
      <ChartCard title="Loan mix">
        <div />
      </ChartCard>,
    );
    expect(screen.queryByRole("link", { name: /See all/i })).not.toBeInTheDocument();
  });
});
