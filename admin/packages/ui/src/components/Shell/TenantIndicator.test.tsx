import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TenantIndicator } from "./TenantIndicator";

describe("TenantIndicator", () => {
  it("renders the tenant name", () => {
    render(<TenantIndicator tenantName="Sacco One" />);
    expect(screen.getByText("Sacco One")).toBeInTheDocument();
  });

  it("shows impersonation badge when impersonating", () => {
    render(<TenantIndicator tenantName="Sacco Two" impersonating />);
    expect(screen.getByText("Impersonating")).toBeInTheDocument();
  });

  it("hides impersonation badge by default", () => {
    render(<TenantIndicator tenantName="Sacco Three" />);
    expect(screen.queryByText("Impersonating")).toBeNull();
  });
});
