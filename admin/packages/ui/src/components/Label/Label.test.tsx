import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Label } from "./Label";

describe("Label", () => {
  it("renders text", () => {
    render(<Label>Member name</Label>);
    expect(screen.getByText("Member name")).toBeInTheDocument();
  });
  it("renders the required asterisk when required", () => {
    render(<Label required>Email</Label>);
    expect(screen.getByText("*")).toBeInTheDocument();
  });
});
