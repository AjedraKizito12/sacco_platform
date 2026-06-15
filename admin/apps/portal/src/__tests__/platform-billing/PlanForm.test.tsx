// admin/apps/portal/src/__tests__/platform-billing/PlanForm.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const createPlan = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { billing: { createPlan } } }),
}));

import { PlanForm } from "../../../app/platform/(authed)/billing/plans/new/_components/PlanForm";

function renderForm() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <PlanForm />
        <Toaster />
      </TenantCurrencyProvider>
    </QueryClientProvider>,
  );
}

describe("PlanForm (create)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("rejects a blank name + code", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: /create plan/i }));
    expect(await screen.findByText(/code is required/i)).toBeInTheDocument();
    expect(createPlan).not.toHaveBeenCalled();
  });

  it("submits a new plan and redirects with a toast", async () => {
    createPlan.mockResolvedValue({ data: { id: "p9" }, error: undefined });
    renderForm();
    await userEvent.type(screen.getByLabelText(/code/i), "growth");
    await userEvent.type(screen.getByLabelText(/^name/i), "Growth");
    await userEvent.type(screen.getByLabelText(/base price/i), "150000");
    await userEvent.click(screen.getByRole("button", { name: /create plan/i }));
    await waitFor(() => expect(createPlan).toHaveBeenCalledTimes(1));
    const [body] = createPlan.mock.calls[0] as [Record<string, unknown>];
    expect(body).toMatchObject({ code: "growth", name: "Growth", base_price: "150000", billing_period: "monthly" });
    await waitFor(() => expect(push).toHaveBeenCalledWith("/platform/billing/plans/p9"));
    expect(await screen.findByText(/plan created/i)).toBeInTheDocument();
  });

  it("includes the selected currency in the submitted payload", async () => {
    createPlan.mockResolvedValue({ data: { id: "p10" }, error: undefined });
    renderForm();
    // Switch currency from UGX (default) to USD.
    await userEvent.click(screen.getByRole("combobox", { name: /currency/i }));
    await userEvent.click(screen.getByRole("option", { name: "USD" }));
    await userEvent.type(screen.getByLabelText(/code/i), "usd-plan");
    await userEvent.type(screen.getByLabelText(/^name/i), "USD Plan");
    await userEvent.type(screen.getByLabelText(/base price/i), "99");
    await userEvent.click(screen.getByRole("button", { name: /create plan/i }));
    await waitFor(() => expect(createPlan).toHaveBeenCalledTimes(1));
    const [body] = createPlan.mock.calls[0] as [Record<string, unknown>];
    expect(body).toMatchObject({ currency: "USD", code: "usd-plan", name: "USD Plan" });
  });

  it("surfaces an error and does not redirect", async () => {
    createPlan.mockResolvedValue({ data: undefined, error: { detail: "Code already exists" } });
    renderForm();
    await userEvent.type(screen.getByLabelText(/code/i), "growth");
    await userEvent.type(screen.getByLabelText(/^name/i), "Growth");
    await userEvent.type(screen.getByLabelText(/base price/i), "150000");
    await userEvent.click(screen.getByRole("button", { name: /create plan/i }));
    expect(await screen.findByText(/code already exists/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
