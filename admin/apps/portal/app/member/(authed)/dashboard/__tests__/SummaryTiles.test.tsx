import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { ReactNode } from "react";
import { SummaryTiles } from "../_components/SummaryTiles";

function wrap(ui: ReactNode) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      {ui}
    </TenantCurrencyProvider>,
  );
}

describe("SummaryTiles", () => {
  it("renders the four headline tiles with computed values", () => {
    wrap(
      <SummaryTiles
        savingsTotal="1240000.00"
        sharesHeld={120}
        sharesValue="1200000.00"
        activeLoans={1}
        feesOutstanding="20000.00"
      />,
    );
    expect(screen.getByText(/Savings/i)).toBeInTheDocument();
    expect(screen.getByText(/Shares/i)).toBeInTheDocument();
    expect(screen.getByText(/Loans/i)).toBeInTheDocument();
    expect(screen.getByText(/Fees/i)).toBeInTheDocument();
  });
});
