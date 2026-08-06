import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Toaster } from "@sacco/ui";
import type { TenantLifecycleEventOut, TenantOut } from "@sacco/schemas";

const cancel = vi.fn();
const restore = vi.fn();
const extendRetention = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { cancel, restore, extendRetention } } }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));

import { OffboardingSection } from "../_components/OffboardingSection";

function makeTenant(overrides: Partial<TenantOut> = {}): TenantOut {
  return {
    id: "t1",
    slug: "acme",
    schema_name: "tenant_acme",
    name: "Acme SACCO",
    status: "active",
    is_active: true,
    provisioning_state: null,
    failed_step: null,
    failure_reason: null,
    provisioning_started_at: null,
    provisioning_completed_at: null,
    seed_version: 1,
    lifecycle_state: "active",
    cancelled_at: null,
    read_only_at: null,
    archived_at: null,
    hard_deleted_at: null,
    retention_hold_until: null,
    archive_storage_key: null,
    archive_size_bytes: null,
    archive_checksum: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderSection(
  tenant: TenantOut,
  events: TenantLifecycleEventOut[] = [],
  canOffboard = true,
) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <OffboardingSection tenant={tenant} events={events} canOffboard={canOffboard} />
      <Toaster />
    </QueryClientProvider>,
  );
}

describe("OffboardingSection", () => {
  beforeEach(() => vi.clearAllMocks());

  it("Cancel goes through the locked maker-checker dialog", async () => {
    renderSection(makeTenant());
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Request Cancellation" }));
    await user.type(
      screen.getByLabelText(/Reason/i),
      "Customer terminated the contract",
    );
    await user.click(screen.getByRole("button", { name: "Continue" }));
    // The locked maker-checker copy (contract V) must be shown.
    expect(
      screen.getByText(/create an approval request, not execute/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create Approval Request" }),
    ).toBeInTheDocument();
  });

  it("Restore uses a plain confirm (no approval request)", async () => {
    restore.mockResolvedValue({ data: {} });
    renderSection(makeTenant({ lifecycle_state: "cancelled", cancelled_at: "2026-02-01T00:00:00Z" }));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Restore" }));
    expect(screen.getByText(/No approval is required/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/create an approval request, not execute/i),
    ).not.toBeInTheDocument();
  });

  it("hides the restore action once physically archived", () => {
    renderSection(
      makeTenant({
        lifecycle_state: "archived",
        archived_at: "2026-03-01T00:00:00Z",
        archive_checksum: "sha256:abc",
      }),
    );
    expect(screen.queryByRole("button", { name: "Restore" })).not.toBeInTheDocument();
  });

  it("hides all actions without the offboard permission", () => {
    renderSection(makeTenant(), [], false);
    expect(
      screen.queryByRole("button", { name: "Request Cancellation" }),
    ).not.toBeInTheDocument();
  });

  it("renders the lifecycle timeline", () => {
    const events: TenantLifecycleEventOut[] = [
      {
        id: "e1",
        from_state: "active",
        to_state: "cancelled",
        occurred_at: "2026-02-01T00:00:00Z",
        reason: "customer left",
        actor_id: null,
        metadata: {},
      },
    ];
    renderSection(makeTenant({ lifecycle_state: "cancelled" }), events);
    expect(screen.getByText(/customer left/i)).toBeInTheDocument();
  });
});
