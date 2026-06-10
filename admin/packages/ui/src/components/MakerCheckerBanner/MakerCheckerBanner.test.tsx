import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MakerCheckerBanner } from "./MakerCheckerBanner";

describe("MakerCheckerBanner", () => {
  it("renders operation + requester + quorum copy", () => {
    render(
      <MakerCheckerBanner
        approvalRequestId="AR-1234"
        operationLabel="Loan disbursement"
        requesterName="Sarah Achieng"
        requestedAt="28 May 2026"
        quorumRequired={2}
        quorumCurrent={1}
        action={<a href="/approvals/AR-1234">View</a>}
      />,
    );
    expect(screen.getByText("Pending Approval")).toBeInTheDocument();
    expect(
      screen.getByText(/Loan disbursement requested by/),
    ).toBeInTheDocument();
    expect(screen.getByText("Sarah Achieng")).toBeInTheDocument();
    expect(
      screen.getByText(/Requires 1 more approval \(1 of 2 so far\)\./),
    ).toBeInTheDocument();
  });

  it("pluralises remaining approvals", () => {
    render(
      <MakerCheckerBanner
        approvalRequestId="AR-1235"
        operationLabel="Reversal"
        requesterName="John Mukasa"
        requestedAt="28 May 2026"
        quorumRequired={3}
        quorumCurrent={1}
        action={<span>view</span>}
      />,
    );
    expect(
      screen.getByText(/Requires 2 more approvals \(1 of 3 so far\)\./),
    ).toBeInTheDocument();
  });
});
