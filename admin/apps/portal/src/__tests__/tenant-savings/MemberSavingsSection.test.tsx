// admin/apps/portal/src/__tests__/tenant-savings/MemberSavingsSection.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { SavingsAccountOut } from "@sacco/schemas";

import { MemberSavingsSection } from "../../../app/(tenant-authed)/members/[id]/_components/MemberSavingsSection";

const account: SavingsAccountOut = {
  id: "a1",
  member_id: "m1",
  savings_product_id: "p1",
  product_name: "Regular Savings",
  interest_rate: "5.00",
  minimum_balance: "500.00",
  liability_account_id: "g1",
};

function renderSection(accounts: SavingsAccountOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <MemberSavingsSection memberId="m1" accounts={accounts} />
    </TenantCurrencyProvider>,
  );
}

describe("MemberSavingsSection", () => {
  it("links each account to its detail and shows the product", () => {
    renderSection([account]);
    expect(screen.getByText("Regular Savings")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View" })).toHaveAttribute(
      "href",
      "/savings/accounts/a1",
    );
  });

  it("the open-account link carries the member_id", () => {
    renderSection([]);
    expect(screen.getByText("No savings accounts.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open account/i })).toHaveAttribute(
      "href",
      "/savings/accounts/new?member_id=m1",
    );
  });
});
