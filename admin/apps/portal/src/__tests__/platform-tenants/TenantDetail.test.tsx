import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { TenantOut } from "@sacco/schemas";

const get = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { get, retryProvisioning: vi.fn() } } }),
}));

import { TenantDetail } from "../../../app/platform/(authed)/tenants/[id]/_components/TenantDetail";

function tenant(over: Partial<TenantOut>): TenantOut {
  return {
    id: "t1", slug: "alpha", schema_name: "tenant_alpha", name: "Alpha SACCO",
    status: "active", is_active: true, provisioning_state: null,
    failed_step: null, failure_reason: null,
    provisioning_started_at: "2026-06-01T00:00:00Z",
    provisioning_completed_at: "2026-06-01T00:01:00Z",
    seed_version: 1, created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:01:00Z",
    ...over,
  };
}

function renderDetail(t: TenantOut, canRetry = false) {
  get.mockResolvedValue({ data: t, error: undefined });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TenantDetail tenant={t} canRetry={canRetry} />
    </QueryClientProvider>,
  );
}

describe("TenantDetail", () => {
  it("renders identity fields and status badge", () => {
    renderDetail(tenant({}));
    expect(screen.getByText("Alpha SACCO")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("tenant_alpha")).toBeInTheDocument();
  });

  it("renders the audit bar wired to the tenant entity", () => {
    const { container } = renderDetail(tenant({}));
    expect(container.querySelector('[data-entity-type="tenant"]')).not.toBeNull();
  });

  it("shows failure details for a failed tenant", () => {
    renderDetail(
      tenant({ status: "failed", failed_step: "run_migrations", failure_reason: "alembic timeout" }),
    );
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText(/run_migrations/)).toBeInTheDocument();
    expect(screen.getByText(/alembic timeout/)).toBeInTheDocument();
  });

  it("does not render a retry button for a non-failed tenant even with permission", () => {
    renderDetail(tenant({ status: "active" }), true);
    expect(screen.queryByRole("button", { name: /request provisioning retry/i })).toBeNull();
  });
});
