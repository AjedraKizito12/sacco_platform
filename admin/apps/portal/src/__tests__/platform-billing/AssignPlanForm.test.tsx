// admin/apps/portal/src/__tests__/platform-billing/AssignPlanForm.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { SubscriptionPlanOut } from "@sacco/schemas";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const assignPlan = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { assignPlan } } }),
}));

import { AssignPlanForm } from "../../../app/platform/(authed)/tenants/[id]/assign-plan/_components/AssignPlanForm";

// Plan ids must be real UUIDs — assignPlanSchema validates plan_id as a uuid.
const STARTER_ID = "11111111-1111-1111-1111-111111111111";
const GROWTH_ID = "22222222-2222-2222-2222-222222222222";

function plan(over: Partial<SubscriptionPlanOut>): SubscriptionPlanOut {
  return {
    id: STARTER_ID, code: "starter", name: "Starter", description: null, currency: "UGX",
    base_price: "50000", per_user_price: "0", per_member_price: "0",
    billing_period: "monthly", member_limit: null, user_limit: null, features: {},
    trial_period_days: 0, grace_period_days: 30, is_active: true,
    created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
    ...over,
  };
}

function renderForm() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AssignPlanForm tenantId="t1" plans={[plan({ id: STARTER_ID, name: "Starter" }), plan({ id: GROWTH_ID, name: "Growth" })]} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("AssignPlanForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("requires a plan selection", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: /assign plan/i }));
    expect(await screen.findByText(/select a plan/i)).toBeInTheDocument();
    expect(assignPlan).not.toHaveBeenCalled();
  });

  it("assigns the selected plan and redirects to the new subscription", async () => {
    assignPlan.mockResolvedValue({ data: { id: "s9" }, error: undefined });
    renderForm();
    await userEvent.click(screen.getByRole("combobox", { name: /plan/i }));
    await userEvent.click(await screen.findByRole("option", { name: /growth/i }));
    await userEvent.click(screen.getByRole("button", { name: /assign plan/i }));
    await waitFor(() => expect(assignPlan).toHaveBeenCalledWith("t1", { plan_id: GROWTH_ID }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/platform/billing/subscriptions/s9"));
    expect(await screen.findByText(/plan assigned/i)).toBeInTheDocument();
  });

  it("surfaces a 409 (tenant already has a live subscription)", async () => {
    assignPlan.mockResolvedValue({ data: undefined, error: { detail: "Tenant already has a live subscription" } });
    renderForm();
    await userEvent.click(screen.getByRole("combobox", { name: /plan/i }));
    await userEvent.click(await screen.findByRole("option", { name: /starter/i }));
    await userEvent.click(screen.getByRole("button", { name: /assign plan/i }));
    expect(await screen.findByText(/already has a live subscription/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
