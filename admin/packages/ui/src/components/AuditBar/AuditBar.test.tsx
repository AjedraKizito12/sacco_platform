import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AuditBar } from "./AuditBar";

describe("AuditBar", () => {
  it("renders the placeholder copy + disabled history button", () => {
    render(<AuditBar entityType="loan" entityId="L-001" />);
    expect(
      screen.getByText(/Audit history coming soon/),
    ).toBeInTheDocument();
    expect(screen.getByText("View Full History")).toBeDisabled();
  });

  it("exposes entity props via data attributes for future consumers", () => {
    const { container } = render(
      <AuditBar entityType="member" entityId="M-2026-0042" />,
    );
    const section = container.querySelector("section");
    expect(section).toHaveAttribute("data-entity-type", "member");
    expect(section).toHaveAttribute("data-entity-id", "M-2026-0042");
  });
});
