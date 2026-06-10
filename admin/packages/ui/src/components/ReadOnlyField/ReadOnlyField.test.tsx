import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReadOnlyField } from "./ReadOnlyField";

describe("ReadOnlyField", () => {
  it("renders label + value", () => {
    render(<ReadOnlyField label="Member ID" value="M-2026-0042" />);
    expect(screen.getByText("Member ID")).toBeInTheDocument();
    expect(screen.getByText("M-2026-0042")).toBeInTheDocument();
  });

  it("accepts ReactNode values", () => {
    render(<ReadOnlyField label="Status" value={<strong>Active</strong>} />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });
});
