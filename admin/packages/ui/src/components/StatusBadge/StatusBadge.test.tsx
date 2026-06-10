import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders loan status with mapped label", () => {
    render(<StatusBadge entity="loan" status="in_arrears" />);
    expect(screen.getByText("In Arrears")).toBeInTheDocument();
  });

  it("renders tenant status", () => {
    render(<StatusBadge entity="tenant" status="suspended" />);
    expect(screen.getByText("Suspended")).toBeInTheDocument();
  });

  it("falls back to neutral with raw value for unknown status", () => {
    render(<StatusBadge entity="loan" status="quantum_state" />);
    expect(screen.getByText("quantum_state")).toBeInTheDocument();
  });

  it("respects label override", () => {
    render(<StatusBadge entity="loan" status="closed" label="Wrapped up" />);
    expect(screen.getByText("Wrapped up")).toBeInTheDocument();
  });

  it("renders payment pending with the friendly label", () => {
    render(<StatusBadge entity="payment" status="pending" />);
    expect(screen.getByText("Pending Confirmation")).toBeInTheDocument();
  });
});
