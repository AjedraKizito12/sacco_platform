import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";

const retryProvisioning = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { retryProvisioning } } }),
}));

import { RetryProvisioningButton } from "../../../app/platform/(authed)/tenants/[id]/_components/RetryProvisioningButton";

const failed: TenantOut = {
  id: "t2", slug: "beta", schema_name: "tenant_beta", name: "Beta SACCO",
  status: "failed", is_active: false, provisioning_state: null,
  failed_step: "run_migrations", failure_reason: "alembic timeout",
  provisioning_started_at: "2026-06-11T00:00:00Z", provisioning_completed_at: null,
  seed_version: 1, created_at: "2026-06-11T00:00:00Z", updated_at: "2026-06-11T00:00:00Z",
};

function renderButton() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RetryProvisioningButton tenant={failed} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("RetryProvisioningButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("opens the locked maker-checker dialog and does not call the API until confirmed", async () => {
    retryProvisioning.mockResolvedValue({ data: failed, error: undefined });
    renderButton();
    await userEvent.click(
      screen.getByRole("button", { name: /request provisioning retry/i }),
    );
    expect(
      await screen.findByText(/create an approval request, not execute/i),
    ).toBeInTheDocument();
    expect(retryProvisioning).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getByRole("button", { name: /create approval request/i }),
    );
    await waitFor(() => expect(retryProvisioning).toHaveBeenCalledWith("t2"));
    expect(await screen.findByText(/approval request created/i)).toBeInTheDocument();
  });

  it("surfaces an error and keeps the dialog open when the request fails", async () => {
    retryProvisioning.mockResolvedValue({
      data: undefined,
      error: { detail: "retry-provisioning requires status='failed', got 'active'" },
    });
    renderButton();
    await userEvent.click(
      screen.getByRole("button", { name: /request provisioning retry/i }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: /create approval request/i }),
    );
    expect(await screen.findByText(/requires status='failed'/i)).toBeInTheDocument();
    expect(
      screen.getByText(/create an approval request, not execute/i),
    ).toBeInTheDocument();
  });
});
