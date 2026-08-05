"use client";

import { useState } from "react";
import {
  Button,
  Count,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@sacco/ui";
import { queryKeys, useTypedQuery } from "@sacco/api-client";
import type { TenantRateLimitLiveOut } from "@sacco/schemas";
import { useAuth } from "@/auth/use-auth";

interface TenantOption {
  id: string;
  name: string;
}

export function TenantLivePanel({ tenants }: { tenants: TenantOption[] }) {
  const { resources } = useAuth();
  const [tenantId, setTenantId] = useState<string>("");

  const query = useTypedQuery<TenantRateLimitLiveOut>(
    queryKeys.rateLimits.tenantLive(tenantId),
    async () => {
      const res = (await resources.rateLimits.getTenantLive(tenantId)) as {
        data?: TenantRateLimitLiveOut;
        error?: unknown;
      };
      if (!res.data) {
        throw new Error("Failed to load live rate-limit consumption");
      }
      return res.data;
    },
    { enabled: tenantId !== "", staleTime: 0 },
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-[13px] text-[var(--text-secondary)]">Tenant</span>
          <Select value={tenantId} onValueChange={setTenantId}>
            <SelectTrigger className="w-72" aria-label="Tenant">
              <SelectValue placeholder="Select a tenant…" />
            </SelectTrigger>
            <SelectContent>
              {tenants.map((t) => (
                <SelectItem key={t.id} value={t.id}>
                  {t.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {tenantId !== "" ? (
          <Button
            variant="secondary"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
          >
            Refresh
          </Button>
        ) : null}
      </div>

      {tenantId === "" ? (
        <p className="text-[13px] text-[var(--text-secondary)]">
          Select a tenant to see live consumption.
        </p>
      ) : query.isPending ? (
        <p className="text-[13px] text-[var(--text-secondary)]">Loading…</p>
      ) : query.isError ? (
        <p className="text-[13px] text-[var(--color-text-danger)]">
          Couldn&apos;t load live consumption.
        </p>
      ) : query.data.buckets.length === 0 ? (
        <p className="text-[13px] text-[var(--text-secondary)]">
          No policies apply to this tenant&apos;s users.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {query.data.buckets.map((b) => {
            const used = b.limit - b.remaining;
            const pct = b.limit > 0 ? Math.round((used / b.limit) * 100) : 0;
            return (
              <li key={b.policy} className="flex flex-col gap-1">
                <div className="flex items-center justify-between text-[13px]">
                  <span className="font-mono">{b.policy}</span>
                  <span className="text-[var(--text-secondary)]">
                    <Count value={b.remaining} /> / <Count value={b.limit} /> left
                  </span>
                </div>
                <div
                  className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-sunken)]"
                  role="progressbar"
                  aria-valuenow={pct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${b.policy} usage`}
                >
                  <div
                    className="h-full rounded-full bg-[var(--color-accent-700)]"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
