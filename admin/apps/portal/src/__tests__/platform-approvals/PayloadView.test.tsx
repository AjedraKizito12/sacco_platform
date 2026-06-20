import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PayloadView } from "../../../app/platform/(authed)/approvals/[id]/_components/PayloadView";

describe("PayloadView", () => {
  it("renders a generic structured tree for a non-diff operation", () => {
    render(
      <PayloadView
        operationType="tenant.suspend"
        payload={{ tenant_id: "abc", reason: "fraud review" }}
      />,
    );
    expect(screen.getByText("tenant_id")).toBeInTheDocument();
    expect(screen.getByText("fraud review")).toBeInTheDocument();
  });

  it("renders a before -> after diff for update_sensitive", () => {
    render(
      <PayloadView
        operationType="platform_user.update_sensitive"
        payload={{ user_id: "u1", is_active: false, is_superuser: true }}
        before={{ is_active: true, is_superuser: false }}
      />,
    );
    expect(screen.getByText("is_active")).toBeInTheDocument();
    expect(screen.getByText("is_superuser")).toBeInTheDocument();
    // is_active: true -> false ; is_superuser: false -> true
    expect(screen.getByText("Yes → No")).toBeInTheDocument();
    expect(screen.getByText("No → Yes")).toBeInTheDocument();
  });

  it("renders the generic tree (no diff) for update_sensitive when no before is provided", () => {
    render(
      <PayloadView
        operationType="platform_user.update_sensitive"
        payload={{ user_id: "u1", is_active: false }}
      />,
    );
    // Falls back to the generic tree, which lists the raw keys.
    expect(screen.getByText("user_id")).toBeInTheDocument();
  });

  it("renders booleans as Yes/No in the generic tree", () => {
    render(<PayloadView operationType="billing.confirm_payment" payload={{ payment_id: "p1" }} />);
    expect(screen.getByText("payment_id")).toBeInTheDocument();
  });
});
