// admin/apps/portal/src/__tests__/tenant-credit/MemberLoansSection.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { LoanOut } from "@sacco/schemas";

import { MemberLoansSection } from "../../../app/(tenant-authed)/members/[id]/_components/MemberLoansSection";

const loan: LoanOut = {
  id: "l1", loan_reference: "LN-202606-000001", loan_application_id: "a1",
  loan_product_id: "p1", member_id: "m1", status: "disbursed",
  principal_amount: "1000000.00", outstanding_principal: "900000.00",
  accrued_interest: "0.00", accrued_penalties: "0.00",
  annual_interest_rate: "18.50", interest_method: "reducing_balance",
  repayment_frequency: "monthly", term_periods: 12,
  disbursement_destination: "cash", first_repayment_due: "2026-07-01",
  maturity_date: "2027-06-01", disbursed_at: "2026-06-21T00:00:00Z",
  created_at: "2026-06-21T00:00:00Z",
};

function renderSection(loans: LoanOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <MemberLoansSection loans={loans} />
    </TenantCurrencyProvider>,
  );
}

describe("MemberLoansSection", () => {
  it("links each loan to its detail and shows the status", () => {
    renderSection([loan]);
    expect(screen.getByText("LN-202606-000001")).toBeInTheDocument();
    expect(screen.getByText("Disbursed")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View" })).toHaveAttribute(
      "href",
      "/credit/loans/l1",
    );
  });

  it("shows the empty state", () => {
    renderSection([]);
    expect(screen.getByText("No loans.")).toBeInTheDocument();
  });
});
