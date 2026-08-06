import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

const reactivate = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { reactivate } } }),
}));

import { TenantActions } from "../../../app/platform/(authed)/tenants/[id]/_components/TenantActions";

function tenant(over: Partial<TenantOut>): TenantOut {
  return {
    id: "t1", slug: "alpha", schema_name: "tenant_alpha", name: "Alpha SACCO",
    status: "active", is_active: true, provisioning_state: null,
    failed_step: null, failure_reason: null, provisioning_started_at: null,
    provisioning_completed_at: "2026-06-01T00:00:00Z", seed_version: 1, lifecycle_state: "active", cancelled_at: null, read_only_at: null, archived_at: null, hard_deleted_at: null, retention_hold_until: null, archive_storage_key: null, archive_size_bytes: null, archive_checksum: null,
    created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
    ...over,
  };
}

function renderActions(t: TenantOut, caps: { canWrite?: boolean; canImpersonate?: boolean; canAssignPlan?: boolean } = {}) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TenantActions tenant={t} canWrite={caps.canWrite ?? true} canImpersonate={caps.canImpersonate ?? true} canAssignPlan={caps.canAssignPlan ?? true} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("TenantActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
  });

  it("shows Edit + Suspend + Impersonate for an active tenant with full perms", () => {
    renderActions(tenant({ status: "active" }));
    expect(screen.getByRole("link", { name: /edit/i })).toHaveAttribute("href", "/platform/tenants/t1/edit");
    expect(screen.getByRole("link", { name: /suspend/i })).toHaveAttribute("href", "/platform/tenants/t1/suspend");
    expect(screen.getByRole("link", { name: /impersonate/i })).toHaveAttribute("href", "/platform/tenants/t1/impersonate");
    expect(screen.queryByRole("button", { name: /reactivate/i })).toBeNull();
  });

  it("shows Reactivate (not Suspend) for a suspended tenant", () => {
    renderActions(tenant({ status: "suspended" }));
    expect(screen.getByRole("button", { name: /reactivate/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /suspend/i })).toBeNull();
  });

  it("hides write actions without write permission but keeps impersonate", () => {
    renderActions(tenant({ status: "active" }), { canWrite: false, canImpersonate: true });
    expect(screen.queryByRole("link", { name: /edit/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /suspend/i })).toBeNull();
    expect(screen.getByRole("link", { name: /impersonate/i })).toBeInTheDocument();
  });

  it("shows Assign plan when canAssignPlan", () => {
    renderActions(tenant({ status: "active" }), { canAssignPlan: true });
    expect(screen.getByRole("link", { name: /assign plan/i })).toHaveAttribute(
      "href",
      "/platform/tenants/t1/assign-plan",
    );
  });

  it("hides Assign plan when canAssignPlan is false", () => {
    renderActions(tenant({ status: "active" }), { canAssignPlan: false });
    expect(screen.queryByRole("link", { name: /assign plan/i })).toBeNull();
  });

  it("reactivates via the confirm dialog and toasts", async () => {
    reactivate.mockResolvedValue({ data: tenant({ status: "active" }), error: undefined });
    renderActions(tenant({ status: "suspended" }));
    await userEvent.click(screen.getByRole("button", { name: /^reactivate$/i }));
    // dialog confirm button is labelled "Reactivate tenant"
    await userEvent.click(screen.getByRole("button", { name: /reactivate tenant/i }));
    await waitFor(() => expect(reactivate).toHaveBeenCalledWith("t1"));
    expect(await screen.findByText(/tenant reactivated/i)).toBeInTheDocument();
  });
});
