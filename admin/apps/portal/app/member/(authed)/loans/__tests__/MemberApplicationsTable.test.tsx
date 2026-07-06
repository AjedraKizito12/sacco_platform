import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { TenantCurrencyProvider } from "@sacco/ui";
import {
  MemberApplicationsTable,
  type MemberApplicationRow,
} from "../_components/MemberApplicationsTable";

function renderTable(rows: MemberApplicationRow[]) {
  return render(
    <NuqsTestingAdapter>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <MemberApplicationsTable rows={rows} />
      </TenantCurrencyProvider>
    </NuqsTestingAdapter>,
  );
}

describe("MemberApplicationsTable", () => {
  it("links each row to the application detail page", () => {
    const { container } = renderTable([
      {
        id: "app-1",
        loan_product_id: "p-1",
        requested_amount: "1000.00",
        requested_term_periods: 12,
        status: "under_review",
      },
    ]);
    // Query by href, not by the rendered Money text (currency formatting varies).
    expect(
      container.querySelector('a[href="/member/loans/applications/app-1"]'),
    ).not.toBeNull();
  });

  it("shows an empty state when there are no applications", () => {
    renderTable([]);
    expect(screen.getByText(/no (loan )?applications/i)).toBeInTheDocument();
  });
});
