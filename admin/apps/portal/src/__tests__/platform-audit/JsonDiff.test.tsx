import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JsonDiff } from "../../components/audit/JsonDiff";

describe("JsonDiff", () => {
  it("shows old and new for a changed key (update)", () => {
    render(<JsonDiff before={{ status: "active" }} after={{ status: "suspended" }} />);
    expect(screen.getByText("status")).toBeInTheDocument();
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getByText("suspended")).toBeInTheDocument();
  });

  it("renders insert (null before) and delete (null after)", () => {
    const { rerender } = render(<JsonDiff before={null} after={{ a: 1 }} />);
    expect(screen.getByText("a")).toBeInTheDocument();
    rerender(<JsonDiff before={{ a: 1 }} after={null} />);
    expect(screen.getByText("a")).toBeInTheDocument();
  });

  it("shows a hint when both sides are empty", () => {
    render(<JsonDiff before={null} after={null} />);
    expect(screen.getByText(/no field-level detail/i)).toBeInTheDocument();
  });
});
