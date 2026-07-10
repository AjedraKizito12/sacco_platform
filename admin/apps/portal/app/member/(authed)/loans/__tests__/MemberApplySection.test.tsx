import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@sacco/ui";
import type { MemberLoanProductOut } from "@sacco/schemas";

const applyForLoan = vi.fn();
const refresh = vi.fn();

vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { member: { applyForLoan } } }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push: vi.fn(), back: vi.fn() }),
}));

import { MemberApplySection } from "../_components/MemberApplySection";

const PRODUCTS: MemberLoanProductOut[] = [
  {
    id: "018f6a3e-1111-7000-8000-000000000001",
    name: "School Fees Loan",
    description: null,
    interest_method: "flat",
    annual_interest_rate: "12.00",
    repayment_frequency: "monthly",
    max_term_periods: 24,
    min_amount: "1000.00",
    max_amount: "50000.00",
  },
];

function renderSection(products: MemberLoanProductOut[] = PRODUCTS) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemberApplySection products={products} />
      <Toaster />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  applyForLoan.mockReset();
  refresh.mockReset();
});

describe("MemberApplySection", () => {
  it("opens the dialog and shows the selected product's bounds as helper text", async () => {
    const user = userEvent.setup();
    renderSection();
    await user.click(screen.getByRole("button", { name: /apply for a loan/i }));
    await user.click(screen.getByRole("combobox", { name: /product/i }));
    await user.click(await screen.findByRole("option", { name: /school fees loan/i }));
    expect(screen.getByText(/up to 24/i)).toBeInTheDocument();
  });

  it("submits a valid application and refreshes", async () => {
    applyForLoan.mockResolvedValue({
      data: { id: "app-1", status: "submitted" },
    });
    const user = userEvent.setup();
    renderSection();
    await user.click(screen.getByRole("button", { name: /apply for a loan/i }));
    await user.click(screen.getByRole("combobox", { name: /product/i }));
    await user.click(await screen.findByRole("option", { name: /school fees loan/i }));
    await user.type(screen.getByLabelText(/amount/i), "5000");
    await user.type(screen.getByLabelText(/term/i), "12");
    await user.type(screen.getByLabelText(/purpose/i), "School fees for my daughter");
    await user.click(screen.getByRole("button", { name: /submit application/i }));
    await waitFor(() => expect(applyForLoan).toHaveBeenCalledTimes(1));
    expect(applyForLoan.mock.calls[0]![0]).toMatchObject({
      loan_product_id: PRODUCTS[0]!.id,
      requested_amount: "5000",
      requested_term_periods: "12",
    });
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("blocks a too-short purpose", async () => {
    const user = userEvent.setup();
    renderSection();
    await user.click(screen.getByRole("button", { name: /apply for a loan/i }));
    await user.click(screen.getByRole("combobox", { name: /product/i }));
    await user.click(await screen.findByRole("option", { name: /school fees loan/i }));
    await user.type(screen.getByLabelText(/amount/i), "5000");
    await user.type(screen.getByLabelText(/term/i), "12");
    await user.type(screen.getByLabelText(/purpose/i), "short");
    await user.click(screen.getByRole("button", { name: /submit application/i }));
    expect(await screen.findByText(/at least 10 characters/i)).toBeInTheDocument();
    expect(applyForLoan).not.toHaveBeenCalled();
  });

  it("renders nothing when there are no products", () => {
    renderSection([]);
    expect(
      screen.queryByRole("button", { name: /apply for a loan/i }),
    ).not.toBeInTheDocument();
  });
});
