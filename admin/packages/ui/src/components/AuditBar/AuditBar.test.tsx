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

  it("renders entries + an enabled View Full History link when entries provided", () => {
    render(
      <AuditBar
        entityType="tenant"
        entityId="t1"
        viewAllHref="/platform/audit?f_record_id=t1"
        entries={[
          {
            id: "a1",
            operation: "update",
            actorLabel: "op@test",
            occurredAt: "2026-06-20T10:00:00Z",
          },
        ]}
      />,
    );
    expect(screen.getByText(/op@test/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /view full history/i });
    expect(link).toHaveAttribute("href", "/platform/audit?f_record_id=t1");
  });

  it("shows an empty hint when entries is an empty array", () => {
    render(<AuditBar entityType="tenant" entityId="t1" entries={[]} />);
    expect(screen.getByText(/no recent activity/i)).toBeInTheDocument();
  });
});
