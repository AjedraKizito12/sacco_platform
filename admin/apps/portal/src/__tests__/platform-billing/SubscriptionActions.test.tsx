// admin/apps/portal/src/__tests__/platform-billing/SubscriptionActions.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { SubscriptionOut } from "@sacco/schemas";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const cancelSubscription = vi.fn();
const reactivateSubscription = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { billing: { cancelSubscription, reactivateSubscription } } }),
}));

import { SubscriptionActions } from "../../../app/platform/(authed)/billing/subscriptions/[id]/_components/SubscriptionActions";

function sub(over: Partial<SubscriptionOut>): SubscriptionOut {
  return {
    id: "s1", tenant_id: "t1", plan_id: "p1", status: "active",
    started_at: "2026-06-01T00:00:00Z", current_period_start: "2026-06-01",
    current_period_end: "2026-06-30", grace_period_ends_at: null,
    cancelled_at: null, cancellation_reason: null, next_billing_date: "2026-07-01",
    metadata_json: {}, created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
    ...over,
  };
}

function renderActions(s: SubscriptionOut) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SubscriptionActions subscription={s} canWrite />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("SubscriptionActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("schedules an at-period-end cancel (direct) with a reason", async () => {
    cancelSubscription.mockResolvedValue({ data: { status: "cancellation_scheduled" }, error: undefined });
    renderActions(sub({ status: "active" }));
    await userEvent.click(screen.getByRole("button", { name: /cancel at period end/i }));
    await userEvent.type(screen.getByLabelText(/reason/i), "Customer downgraded plans");
    await userEvent.click(screen.getByRole("button", { name: /schedule cancellation/i }));
    await waitFor(() =>
      expect(cancelSubscription).toHaveBeenCalledWith(
        "s1",
        { reason: "Customer downgraded plans" },
        { mode: "at_period_end" },
      ),
    );
    expect(await screen.findByText(/cancellation scheduled/i)).toBeInTheDocument();
  });

  it("requests an immediate cancel via the maker-checker dialog", async () => {
    cancelSubscription.mockResolvedValue({
      data: { status: "pending_approval", approval_request_id: "ar1" },
      error: undefined,
    });
    renderActions(sub({ status: "active" }));
    await userEvent.click(screen.getByRole("button", { name: /cancel immediately/i }));
    await userEvent.type(screen.getByLabelText(/reason/i), "Fraudulent tenant account");
    await userEvent.click(screen.getByRole("button", { name: /^request/i }));
    expect(await screen.findByText(/create an approval request, not execute/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /create approval request/i }));
    await waitFor(() =>
      expect(cancelSubscription).toHaveBeenCalledWith(
        "s1",
        { reason: "Fraudulent tenant account" },
        { mode: "immediate" },
      ),
    );
    expect(await screen.findByText(/approval request created/i)).toBeInTheDocument();
  });

  it("reactivates a suspended subscription (direct)", async () => {
    reactivateSubscription.mockResolvedValue({ data: { id: "s1", status: "active" }, error: undefined });
    renderActions(sub({ status: "suspended" }));
    await userEvent.click(screen.getByRole("button", { name: /reactivate/i }));
    await userEvent.click(screen.getByRole("button", { name: /reactivate subscription/i }));
    await waitFor(() => expect(reactivateSubscription).toHaveBeenCalledWith("s1"));
    expect(await screen.findByText(/subscription reactivated/i)).toBeInTheDocument();
  });
});
