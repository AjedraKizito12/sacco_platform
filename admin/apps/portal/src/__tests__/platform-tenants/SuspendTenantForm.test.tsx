import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const suspend = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { suspend } } }),
}));

import { SuspendTenantForm } from "../../../app/platform/(authed)/tenants/[id]/suspend/_components/SuspendTenantForm";

const tenant: TenantOut = {
  id: "t1", slug: "alpha", schema_name: "tenant_alpha", name: "Alpha SACCO",
  status: "active", is_active: true, provisioning_state: null,
  failed_step: null, failure_reason: null, provisioning_started_at: null,
  provisioning_completed_at: "2026-06-01T00:00:00Z", seed_version: 1, lifecycle_state: "active", cancelled_at: null, read_only_at: null, archived_at: null, hard_deleted_at: null, retention_hold_until: null, archive_storage_key: null, archive_size_bytes: null, archive_checksum: null,
  created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
};

function renderForm() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SuspendTenantForm tenant={tenant} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("SuspendTenantForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("rejects a reason under 10 characters", async () => {
    renderForm();
    await userEvent.type(screen.getByLabelText(/reason/i), "too short");
    await userEvent.click(screen.getByRole("button", { name: /request suspension/i }));
    expect(await screen.findByText(/at least 10 characters/i)).toBeInTheDocument();
    expect(suspend).not.toHaveBeenCalled();
  });

  it("opens the locked maker-checker dialog and submits on confirm", async () => {
    suspend.mockResolvedValue({
      data: { status: "pending_approval", approval_request_id: "ar1" },
      error: undefined,
    });
    renderForm();
    await userEvent.type(screen.getByLabelText(/reason/i), "Non-payment for 90 days");
    await userEvent.click(screen.getByRole("button", { name: /request suspension/i }));
    expect(await screen.findByText(/create an approval request, not execute/i)).toBeInTheDocument();
    expect(suspend).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /create approval request/i }));
    await waitFor(() =>
      expect(suspend).toHaveBeenCalledWith("t1", { reason: "Non-payment for 90 days" }),
    );
    expect(await screen.findByText(/approval request created/i)).toBeInTheDocument();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/platform/tenants/t1"));
  });

  it("keeps the dialog open and surfaces an error on failure", async () => {
    suspend.mockResolvedValue({
      data: undefined,
      error: { detail: "Tenant is already suspended" },
    });
    renderForm();
    await userEvent.type(screen.getByLabelText(/reason/i), "Non-payment for 90 days");
    await userEvent.click(screen.getByRole("button", { name: /request suspension/i }));
    await userEvent.click(
      await screen.findByRole("button", { name: /create approval request/i }),
    );
    expect(await screen.findByText(/already suspended/i)).toBeInTheDocument();
    expect(screen.getByText(/create an approval request, not execute/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
