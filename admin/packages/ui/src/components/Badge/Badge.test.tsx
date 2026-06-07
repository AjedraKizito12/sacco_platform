import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Badge } from "./Badge";

describe("Badge", () => {
  it("renders children", () => {
    render(<Badge>Approved</Badge>);
    expect(screen.getByText("Approved")).toBeInTheDocument();
  });
  it("renders the leading dot when withDot=true", () => {
    render(<Badge withDot>Pending</Badge>);
    const span = screen.getByText("Pending");
    expect(span.querySelector("[aria-hidden]")).toBeInTheDocument();
  });
});
