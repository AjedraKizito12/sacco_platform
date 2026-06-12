"use client";

import { queryKeys, useTypedQuery } from "@sacco/api-client";
import type { TenantOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";

const IN_FLIGHT_STATUSES = new Set(["pending", "provisioning"]);

/** Terminal provisioning statuses stop the poll loop. */
export function isProvisioningSettled(status: string): boolean {
  return !IN_FLIGHT_STATUSES.has(status);
}

const POLL_INTERVAL_MS = 2000;

/**
 * Live view of a tenant during provisioning. Polls GET /platform/tenants/{id}
 * every 2s while status is pending/provisioning, then stops. Pass the
 * server-fetched tenant as `initialData` so the first paint never waits on a
 * client fetch (contract M).
 */
export function useTenantProvisioning(tenantId: string, initialData?: TenantOut) {
  const { resources } = useAuth();
  return useTypedQuery<TenantOut>(
    queryKeys.tenants.detail(tenantId),
    async () => {
      // resources.tenants.get uses `as never` casts in tenants.ts — cast to
      // the real { data, error } shape that openapi-fetch returns at runtime.
      const res = await (
        resources.tenants.get(tenantId) as Promise<{
          data?: TenantOut;
          error?: unknown;
        }>
      );
      if (res.error) throw res.error;
      if (!res.data) throw new Error("Tenant not found");
      return res.data;
    },
    {
      ...(initialData !== undefined ? { initialData } : {}),
      refetchInterval: (query) => {
        const status = query.state.data?.status;
        if (!status) return POLL_INTERVAL_MS;
        return isProvisioningSettled(status) ? false : POLL_INTERVAL_MS;
      },
    },
  );
}
