import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Count } from "./Count";

describe("Count", () => {
  it("formats with thousands separator", () => {
    render(<Count value={1234567} />);
    expect(screen.getByText("1,234,567")).toBeInTheDocument();
  });
  it("renders zero", () => {
    render(<Count value={0} />);
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});
