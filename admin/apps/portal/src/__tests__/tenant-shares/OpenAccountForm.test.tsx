// admin/apps/portal/src/__tests__/tenant-shares/OpenAccountForm.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const openAccount = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { shares: { openAccount } } }),
}));

import {
  OpenAccountForm,
  type MemberOption,
  type ProductOption,
} from "../../../app/(tenant-authed)/shares/accounts/new/_components/OpenAccountForm";

const MEMBER_A = "550e8400-e29b-41d4-a716-446655440001";
const MEMBER_B = "550e8400-e29b-41d4-a716-446655440002";
const PRODUCT = "550e8400-e29b-41d4-a716-446655440003";

const members: MemberOption[] = [
  { id: MEMBER_A, full_name: "Ada Loan", member_number: "M-0001" },
  { id: MEMBER_B, full_name: "Ben Okello", member_number: "M-0002" },
];
const products: ProductOption[] = [{ id: PRODUCT, name: "Ordinary Shares" }];

function renderForm(defaultMemberId?: string) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <OpenAccountForm
        members={members}
        products={products}
        {...(defaultMemberId ? { defaultMemberId } : {})}
      />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("OpenAccountForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("opens an account and redirects to its detail", async () => {
    openAccount.mockResolvedValue({ data: { id: "a9" }, error: undefined });
    renderForm();
    await userEvent.click(screen.getByLabelText(/member/i));
    await userEvent.click(await screen.findByRole("option", { name: /Ada Loan/ }));
    await userEvent.click(screen.getByLabelText(/product/i));
    await userEvent.click(await screen.findByRole("option", { name: "Ordinary Shares" }));
    await userEvent.click(screen.getByRole("button", { name: /open account/i }));

    expect(await screen.findByText(/account opened/i)).toBeInTheDocument();
    expect(openAccount).toHaveBeenCalledWith({
      member_id: MEMBER_A,
      share_product_id: PRODUCT,
    });
    expect(push).toHaveBeenCalledWith("/shares/accounts/a9");
  });

  it("pre-selects the member from defaultMemberId", async () => {
    openAccount.mockResolvedValue({ data: { id: "a9" }, error: undefined });
    renderForm(MEMBER_B);
    await userEvent.click(screen.getByLabelText(/product/i));
    await userEvent.click(await screen.findByRole("option", { name: "Ordinary Shares" }));
    await userEvent.click(screen.getByRole("button", { name: /open account/i }));

    expect(await screen.findByText(/account opened/i)).toBeInTheDocument();
    expect(openAccount).toHaveBeenCalledWith({
      member_id: MEMBER_B,
      share_product_id: PRODUCT,
    });
  });
});
