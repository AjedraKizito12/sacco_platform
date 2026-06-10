import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("renders title + description + action slot", () => {
    render(
      <EmptyState
        title="No members"
        description="Get started by adding one."
        action={<button>Add member</button>}
      />,
    );
    expect(screen.getByText("No members")).toBeInTheDocument();
    expect(screen.getByText("Get started by adding one.")).toBeInTheDocument();
    expect(screen.getByText("Add member")).toBeInTheDocument();
  });
});
