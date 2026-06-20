import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBreakdown } from "../../../app/platform/(authed)/operations/_components/StatusBreakdown";

describe("StatusBreakdown", () => {
  it("renders a row per status with its count", () => {
    render(
      <StatusBreakdown
        title="Tenants by status"
        entity="tenant"
        counts={{ active: 38, suspended: 3, provisioning: 1 }}
      />,
    );
    expect(screen.getByText("Tenants by status")).toBeInTheDocument();
    expect(screen.getByText("38")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("orders rows by count descending", () => {
    render(
      <StatusBreakdown
        title="Subscriptions by status"
        entity="subscription"
        counts={{ trialing: 4, active: 35, past_due: 2 }}
      />,
    );
    const counts = screen.getAllByTestId("breakdown-count").map((n) => n.textContent);
    expect(counts).toEqual(["35", "4", "2"]);
  });

  it("shows an empty hint when there are no entries", () => {
    render(<StatusBreakdown title="Tenants by status" entity="tenant" counts={{}} />);
    expect(screen.getByText("No data")).toBeInTheDocument();
  });
});
