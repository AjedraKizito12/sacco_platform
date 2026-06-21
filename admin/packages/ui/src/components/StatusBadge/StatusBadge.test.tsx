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

  it("renders a platform_user active status", () => {
    render(<StatusBadge entity="platform_user" status="active" />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("renders a platform_user inactive status", () => {
    render(<StatusBadge entity="platform_user" status="inactive" />);
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });

  it("renders a jwt_key retiring status", () => {
    render(<StatusBadge entity="jwt_key" status="retiring" />);
    expect(screen.getByText("Retiring")).toBeInTheDocument();
  });

  it("maps tenant_user inactive", () => {
    render(<StatusBadge entity="tenant_user" status="inactive" />);
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });

  it("renders a loan_application status", () => {
    render(<StatusBadge entity="loan_application" status="pending" />);
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("renders a guarantor status", () => {
    render(<StatusBadge entity="guarantor" status="accepted" />);
    expect(screen.getByText("Accepted")).toBeInTheDocument();
  });

  it("renders a payroll_batch status", () => {
    render(<StatusBadge entity="payroll_batch" status="pending_review" />);
    expect(screen.getByText("Pending review")).toBeInTheDocument();
  });
});
