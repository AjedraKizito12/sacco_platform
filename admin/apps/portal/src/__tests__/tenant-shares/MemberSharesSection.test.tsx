// admin/apps/portal/src/__tests__/tenant-shares/MemberSharesSection.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TenantCurrencyProvider } from "@sacco/ui";
import type { ShareAccountListItemOut } from "@sacco/schemas";

import { MemberSharesSection } from "../../../app/(tenant-authed)/members/[id]/_components/MemberSharesSection";

const account: ShareAccountListItemOut = {
  id: "a1",
  member_id: "m1",
  share_product_id: "p1",
  product_name: "Ordinary Shares",
  par_value: "1000.00",
  shares_held: 5,
  total_value: "5000.00",
};

function renderSection(accounts: ShareAccountListItemOut[]) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <MemberSharesSection memberId="m1" accounts={accounts} />
    </TenantCurrencyProvider>,
  );
}

describe("MemberSharesSection", () => {
  it("links each account to its detail and shows the product", () => {
    renderSection([account]);
    expect(screen.getByText("Ordinary Shares")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View" })).toHaveAttribute(
      "href",
      "/shares/accounts/a1",
    );
  });

  it("the open-account link carries the member_id", () => {
    renderSection([]);
    expect(screen.getByText("No share accounts.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open account/i })).toHaveAttribute(
      "href",
      "/shares/accounts/new?member_id=m1",
    );
  });
});
