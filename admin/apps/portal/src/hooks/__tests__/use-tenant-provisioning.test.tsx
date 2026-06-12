import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import type { TenantOut } from "@sacco/schemas";

const get = vi.fn();
vi.mock("@/auth/use-auth", () => ({
  useAuth: () => ({ resources: { tenants: { get } } }),
}));

import {
  isProvisioningSettled,
  useTenantProvisioning,
} from "../use-tenant-provisioning";

const active: TenantOut = {
  id: "t1", slug: "alpha", schema_name: "tenant_alpha", name: "Alpha",
  status: "active", is_active: true, provisioning_state: null,
  failed_step: null, failure_reason: null,
  provisioning_started_at: "2026-06-01T00:00:00Z",
  provisioning_completed_at: "2026-06-01T00:01:00Z",
  seed_version: 1, created_at: "2026-06-01T00:00:00Z", updated_at: "2026-06-01T00:01:00Z",
};

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("isProvisioningSettled", () => {
  it("treats pending and provisioning as in-flight", () => {
    expect(isProvisioningSettled("pending")).toBe(false);
    expect(isProvisioningSettled("provisioning")).toBe(false);
  });
  it("treats active, failed, suspended, archived as settled", () => {
    for (const s of ["active", "failed", "suspended", "archived"]) {
      expect(isProvisioningSettled(s)).toBe(true);
    }
  });
});

describe("useTenantProvisioning", () => {
  it("fetches the tenant and exposes it", async () => {
    get.mockResolvedValue({ data: active, error: undefined });
    const { result } = renderHook(() => useTenantProvisioning("t1"), { wrapper });
    await waitFor(() => expect(result.current.data?.status).toBe("active"));
    expect(get).toHaveBeenCalledWith("t1");
  });

  it("serves initialData without waiting for a fetch", () => {
    get.mockResolvedValue({ data: active, error: undefined });
    const { result } = renderHook(() => useTenantProvisioning("t1", active), {
      wrapper,
    });
    expect(result.current.data?.id).toBe("t1");
  });
});
