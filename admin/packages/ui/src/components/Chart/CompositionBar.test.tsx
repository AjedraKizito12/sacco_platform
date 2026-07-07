import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { CompositionBar } from "./CompositionBar";

describe("CompositionBar", () => {
  it("renders a legend row and a bar segment per category", () => {
    render(
      <CompositionBar
        data={[
          { label: "Active", value: 60 },
          { label: "Suspended", value: 40 },
        ]}
      />,
    );
    // legend
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Suspended")).toBeInTheDocument();
    expect(screen.getByText("60")).toBeInTheDocument();
    // stacked bar segment carries its share as an accessible label
    expect(screen.getByTitle("Active: 60%")).toBeInTheDocument();
  });

  it("formats legend values through valueFormatter", () => {
    render(
      <CompositionBar
        data={[{ label: "Tenants", value: 12 }]}
        valueFormatter={(v) => `${v} total`}
      />,
    );
    expect(screen.getByText("12 total")).toBeInTheDocument();
  });

  it("renders the empty state when every category is zero", () => {
    render(
      <CompositionBar data={[{ label: "Active", value: 0 }]} emptyLabel="No tenants" />,
    );
    expect(screen.getByText("No tenants")).toBeInTheDocument();
  });
});
