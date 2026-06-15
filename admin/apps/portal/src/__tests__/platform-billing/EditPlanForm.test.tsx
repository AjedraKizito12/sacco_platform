// admin/apps/portal/src/__tests__/platform-billing/EditPlanForm.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TenantCurrencyProvider, Toaster, toast } from "@sacco/ui";
import type { SubscriptionPlanOut } from "@sacco/schemas";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const patchPlan = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { billing: { patchPlan } } }),
}));

import { EditPlanForm } from "../../../app/platform/(authed)/billing/plans/[id]/edit/_components/EditPlanForm";

const plan: SubscriptionPlanOut = {
  id: "p1", code: "starter", name: "Starter", description: null, currency: "UGX",
  base_price: "50000", per_user_price: "0", per_member_price: "0",
  billing_period: "monthly", member_limit: null, user_limit: null, features: {},
  trial_period_days: 0, grace_period_days: 30, is_active: true,
  created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
};

function renderForm() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
        <EditPlanForm plan={plan} />
        <Toaster />
      </TenantCurrencyProvider>
    </QueryClientProvider>,
  );
}

describe("EditPlanForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("submits the changed name + redirects to detail with a toast", async () => {
    patchPlan.mockResolvedValue({ data: { ...plan, name: "Starter+" }, error: undefined });
    renderForm();
    await userEvent.clear(screen.getByLabelText(/^name/i));
    await userEvent.type(screen.getByLabelText(/^name/i), "Starter+");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(patchPlan).toHaveBeenCalledWith("p1", expect.objectContaining({ name: "Starter+" })),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/platform/billing/plans/p1"));
    expect(await screen.findByText(/changes saved/i)).toBeInTheDocument();
  });

  it("surfaces an error and does not redirect", async () => {
    patchPlan.mockResolvedValue({ data: undefined, error: { detail: "Plan not found" } });
    renderForm();
    await userEvent.clear(screen.getByLabelText(/^name/i));
    await userEvent.type(screen.getByLabelText(/^name/i), "Starter+");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText(/plan not found/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
