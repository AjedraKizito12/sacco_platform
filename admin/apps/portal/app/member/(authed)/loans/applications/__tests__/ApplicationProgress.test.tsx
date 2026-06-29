import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TenantCurrencyProvider } from "@sacco/ui";
import {
  ApplicationProgress,
  type ApplicationDetail,
} from "../[id]/_components/ApplicationProgress";

const base: ApplicationDetail = {
  id: "app-1",
  status: "under_review",
  requested_amount: "1000.00",
  requested_term_periods: 12,
  approved_amount: null,
  approved_term_periods: null,
  rejection_reason: null,
  reviewed_at: "2026-06-29T10:00:00Z",
  decided_at: null,
};

function renderProgress(application: ApplicationDetail) {
  return render(
    <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
      <ApplicationProgress application={application} />
    </TenantCurrencyProvider>,
  );
}

describe("ApplicationProgress", () => {
  it("renders the progress stepper for an in-flight application", () => {
    renderProgress(base);
    expect(screen.getByRole("list", { name: /progress/i })).toBeInTheDocument();
    expect(screen.getByText(/under review/i)).toBeInTheDocument();
  });

  it("shows the rejection reason for a rejected application", () => {
    renderProgress({
      ...base,
      status: "rejected",
      rejection_reason: "Insufficient savings history",
      decided_at: "2026-06-29T12:00:00Z",
    });
    expect(screen.getByText(/insufficient savings history/i)).toBeInTheDocument();
  });
});
