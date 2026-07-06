import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TrendAreaChart } from "./TrendAreaChart";

const SERIES = [
  { label: "Jan", value: 100 },
  { label: "Feb", value: 140 },
  { label: "Mar", value: 180 },
];

describe("TrendAreaChart", () => {
  it("exposes an accessible summary with the latest value", () => {
    render(
      <TrendAreaChart
        data={SERIES}
        ariaLabel="Savings growth"
        valueFormat={{ kind: "money", currency: "UGX" }}
      />,
    );
    const fig = screen.getByRole("img", { name: /Savings growth/i });
    expect(fig).toBeInTheDocument();
    // latest point surfaced for SR users / tests
    expect(screen.getByText("UGX 180")).toBeInTheDocument();
  });

  it("renders an empty state when there is no data", () => {
    render(<TrendAreaChart data={[]} ariaLabel="Revenue" emptyLabel="No history yet" />);
    expect(screen.getByText("No history yet")).toBeInTheDocument();
  });
});
