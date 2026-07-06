import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { CompositionDonut } from "./CompositionDonut";

describe("CompositionDonut", () => {
  it("renders a legend row per segment with value and percentage", () => {
    render(
      <CompositionDonut
        data={[
          { label: "Active", value: 75 },
          { label: "Pending", value: 25 },
        ]}
      />,
    );
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    // value + rounded percentage both appear in the legend
    expect(screen.getByText("75")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
  });

  it("formats values through valueFormatter", () => {
    render(
      <CompositionDonut
        data={[{ label: "Savings", value: 1000 }]}
        valueFormatter={(v) => `UGX ${v}`}
      />,
    );
    expect(screen.getByText("UGX 1000")).toBeInTheDocument();
  });

  it("renders the empty state when every segment is zero", () => {
    render(
      <CompositionDonut
        data={[{ label: "Active", value: 0 }]}
        emptyLabel="No loans yet"
      />,
    );
    expect(screen.getByText("No loans yet")).toBeInTheDocument();
    expect(screen.queryByText("Active")).not.toBeInTheDocument();
  });
});
