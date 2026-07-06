import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { KycCompletionOut } from "@sacco/schemas";
import { KycCompletionCard } from "../KycCompletionCard";

const incomplete: KycCompletionOut = {
  items: [
    { key: "legal_name", label: "Registered legal name", required: true, present: true },
    { key: "tax_id", label: "Tax identification number", required: true, present: false },
    { key: "postal_address", label: "Postal address", required: false, present: false },
  ],
  required_total: 2,
  required_present: 1,
  percent: 50,
  missing_required: ["tax_id"],
  is_complete: false,
};

describe("KycCompletionCard", () => {
  it("renders the percent, progress bar, and required-progress summary", () => {
    render(<KycCompletionCard completion={incomplete} />);
    expect(screen.getByText("50.00%")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
    expect(screen.getByText(/1 of 2 required items complete/i)).toBeInTheDocument();
  });

  it("lists every catalog item and marks optional ones", () => {
    render(<KycCompletionCard completion={incomplete} />);
    expect(screen.getByText("Registered legal name")).toBeInTheDocument();
    expect(screen.getByText("Tax identification number")).toBeInTheDocument();
    expect(screen.getByText("Postal address")).toBeInTheDocument();
    expect(screen.getByText("(optional)")).toBeInTheDocument();
  });

  it("shows the all-complete summary when complete", () => {
    render(
      <KycCompletionCard
        completion={{
          ...incomplete,
          required_present: 2,
          percent: 100,
          missing_required: [],
          is_complete: true,
          items: incomplete.items.map((i) => ({ ...i, present: true })),
        }}
      />,
    );
    expect(screen.getByText("100.00%")).toBeInTheDocument();
    expect(screen.getByText(/all required items are complete/i)).toBeInTheDocument();
  });
});
