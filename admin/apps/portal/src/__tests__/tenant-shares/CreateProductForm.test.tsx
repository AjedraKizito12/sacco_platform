// admin/apps/portal/src/__tests__/tenant-shares/CreateProductForm.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createProduct = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { shares: { createProduct } } }),
}));

import {
  CreateProductForm,
  type GlAccountOption,
} from "../../../app/(tenant-authed)/shares/products/new/_components/CreateProductForm";

const GL_ID = "550e8400-e29b-41d4-a716-446655440010";
const glAccounts: GlAccountOption[] = [
  { id: GL_ID, code: "3010", name: "Share Capital", account_type: "equity" },
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
    await userEvent.type(screen.getByLabelText(/name/i), "Ordinary Shares");
    await userEvent.type(screen.getByLabelText(/par value/i), "1000");
    const minField = screen.getByLabelText(/minimum shares/i);
    await userEvent.clear(minField);
    await userEvent.type(minField, "5");
    await userEvent.click(screen.getByLabelText(/share capital gl account/i));
    await userEvent.click(await screen.findByRole("option", { name: /Share Capital/ }));
    await userEvent.click(screen.getByRole("button", { name: /create product/i }));

    expect(await screen.findByText(/product created/i)).toBeInTheDocument();
    const call = createProduct.mock.calls[0]![0];
    expect(call).toMatchObject({
      name: "Ordinary Shares",
      share_capital_account_id: GL_ID,
      minimum_shares: "5",
    });
    expect(call).not.toHaveProperty("maximum_shares");
    expect(push).toHaveBeenCalledWith("/shares");
  });
});
