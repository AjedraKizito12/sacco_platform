import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Percentage } from "./Percentage";

describe("Percentage", () => {
  it("renders with two decimal places", () => {
    render(<Percentage value="12.5" />);
    expect(screen.getByText("12.50%")).toBeInTheDocument();
  });
  it("handles integers", () => {
    render(<Percentage value="100" />);
    expect(screen.getByText("100.00%")).toBeInTheDocument();
  });
  it("passes invalid input through unchanged", () => {
    render(<Percentage value="—" />);
    expect(screen.getByText("—%")).toBeInTheDocument();
  });
});
