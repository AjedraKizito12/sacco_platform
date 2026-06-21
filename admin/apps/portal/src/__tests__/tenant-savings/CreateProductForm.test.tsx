// admin/apps/portal/src/__tests__/tenant-savings/CreateProductForm.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createProduct = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { savings: { createProduct } } }),
}));

import {
  CreateProductForm,
  type GlAccountOption,
} from "../../../app/(tenant-authed)/savings/products/new/_components/CreateProductForm";

const GL_ID = "550e8400-e29b-41d4-a716-446655440010";
const glAccounts: GlAccountOption[] = [
  { id: GL_ID, code: "2010", name: "Member Savings", account_type: "liability" },
];

function renderForm() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <CreateProductForm glAccounts={glAccounts} />
      </TenantCurrencyProvider>
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("CreateProductForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("blocks submit on a blank name", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: /create product/i }));
    expect(createProduct).not.toHaveBeenCalled();
  });

  it("creates a product and redirects on success", async () => {
    createProduct.mockResolvedValue({ data: { id: "p9" }, error: undefined });
    renderForm();
    await userEvent.type(screen.getByLabelText(/name/i), "Regular Savings");
    await userEvent.type(screen.getByLabelText(/interest rate/i), "5");
    await userEvent.type(screen.getByLabelText(/minimum balance/i), "500");
    await userEvent.click(screen.getByLabelText(/liability gl account/i));
    await userEvent.click(await screen.findByRole("option", { name: /Member Savings/ }));
    await userEvent.click(screen.getByRole("button", { name: /create product/i }));

    expect(await screen.findByText(/product created/i)).toBeInTheDocument();
    expect(createProduct).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Regular Savings", liability_account_id: GL_ID }),
    );
    expect(push).toHaveBeenCalledWith("/savings");
  });
});
