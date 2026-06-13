import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster, toast } from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";

const requestImp = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { impersonations: { request: requestImp } } }),
}));

const assign = vi.fn();
vi.stubGlobal("location", { assign: assign } as unknown as Location);
const fetchMock = vi.fn();

import { ImpersonateTenantPanel } from "../../../app/platform/(authed)/tenants/[id]/impersonate/_components/ImpersonateTenantPanel";

const tenant: TenantOut = {
  id: "t1", slug: "alpha", schema_name: "tenant_alpha", name: "Alpha SACCO",
  status: "active", is_active: true, provisioning_state: null,
  failed_step: null, failure_reason: null, provisioning_started_at: null,
  provisioning_completed_at: "2026-06-01T00:00:00Z", seed_version: 1,
  created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:00:00Z",
};

function renderPanel(active: Array<{ id: string; expires_at: string }> = []) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ImpersonateTenantPanel tenant={tenant} activeForTenant={active} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("ImpersonateTenantPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    toast.dismiss();
    vi.stubGlobal("fetch", fetchMock);
  });

  it("rejects a short reason and does not submit", async () => {
    renderPanel();
    await userEvent.type(screen.getByLabelText(/reason/i), "debug");
    await userEvent.click(screen.getByRole("button", { name: /request impersonation/i }));
    expect(await screen.findByText(/at least 10 characters/i)).toBeInTheDocument();
    expect(requestImp).not.toHaveBeenCalled();
  });

  it("submits an impersonation request via the locked dialog", async () => {
    requestImp.mockResolvedValue({ data: { approval_request_id: "ar1", status: "pending" }, error: undefined });
    renderPanel();
    await userEvent.type(screen.getByLabelText(/reason/i), "Investigating a posting discrepancy");
    await userEvent.click(screen.getByRole("button", { name: /request impersonation/i }));
    expect(await screen.findByText(/create an approval request, not execute/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /create approval request/i }));
    await waitFor(() =>
      expect(requestImp).toHaveBeenCalledWith({
        tenant_id: "t1",
        reason: "Investigating a posting discrepancy",
      }),
    );
    expect(await screen.findByText(/approval request created/i)).toBeInTheDocument();
  });

  it("enters an approved session: activates then navigates to tenant context", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ access_token: "ta", expires_in: 900, tenant_slug: "alpha" }),
    });
    renderPanel([{ id: "imp1", expires_at: "2026-06-13T12:30:00Z" }]);
    await userEvent.click(screen.getByRole("button", { name: /enter session/i }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/impersonation/activate",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/"));
  });

  it("toasts when entering a session fails (e.g. expired)", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 410, json: async () => ({ detail: "session expired" }) });
    renderPanel([{ id: "imp1", expires_at: "2026-06-13T12:30:00Z" }]);
    await userEvent.click(screen.getByRole("button", { name: /enter session/i }));
    expect(await screen.findByText(/session expired/i)).toBeInTheDocument();
    expect(assign).not.toHaveBeenCalled();
  });
});
