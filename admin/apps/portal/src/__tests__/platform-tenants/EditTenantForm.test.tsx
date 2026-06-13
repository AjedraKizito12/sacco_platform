import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const patch = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { patch } } }),
}));

import { EditTenantForm } from "../../../app/platform/(authed)/tenants/[id]/edit/_components/EditTenantForm";

const tenant: TenantOut = {
  id: "t1", slug: "alpha", schema_name: "tenant_alpha", name: "Alpha SACCO",
  status: "active", is_active: true, provisioning_state: null,
  failed_step: null, failure_reason: null, provisioning_started_at: null,
  provisioning_completed_at: "2026-06-01T00:00:00Z", seed_version: 1,
  created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
};

function renderForm() {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <EditTenantForm tenant={tenant} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("EditTenantForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("rejects a blank name", async () => {
    renderForm();
    await userEvent.clear(screen.getByLabelText(/name/i));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText(/name is required/i)).toBeInTheDocument();
    expect(patch).not.toHaveBeenCalled();
  });

  it("submits the new name and redirects to detail with a toast", async () => {
    patch.mockResolvedValue({ data: { ...tenant, name: "Renamed" }, error: undefined });
    renderForm();
    await userEvent.clear(screen.getByLabelText(/name/i));
    await userEvent.type(screen.getByLabelText(/name/i), "Renamed");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(patch).toHaveBeenCalledWith("t1", { name: "Renamed" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/platform/tenants/t1"));
    expect(await screen.findByText(/changes saved/i)).toBeInTheDocument();
  });

  it("surfaces an error and does not redirect", async () => {
    patch.mockResolvedValue({ data: undefined, error: { detail: "Tenant not found" } });
    renderForm();
    await userEvent.clear(screen.getByLabelText(/name/i));
    await userEvent.type(screen.getByLabelText(/name/i), "Renamed");
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText(/tenant not found/i)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });
});
