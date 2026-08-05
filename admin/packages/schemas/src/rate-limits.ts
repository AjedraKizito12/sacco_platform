// Mirrors app/platform_/rate_limits/schemas.py — the read-only rate-limit
// config + per-tenant live view surfaced at /platform/settings/rate-limits.

export interface RateLimitPolicyOut {
  name: string;
  limit: number;
  window_seconds: number;
}

/** `plan_overrides` is keyed by plan code; each value maps a policy name to a
 * partial override of that policy's limit / window. */
export interface RateLimitConfigOut {
  defaults: RateLimitPolicyOut[];
  plan_overrides: Record<
    string,
    Record<string, { limit?: number; window_seconds?: number }>
  >;
}

export interface TenantRateLimitBucketOut {
  policy: string;
  remaining: number;
  limit: number;
}

export interface TenantRateLimitLiveOut {
  tenant_id: string;
  buckets: TenantRateLimitBucketOut[];
}

/** A single plan × policy override, flattened for table rendering. `id` keeps
 * DataTable row identity stable (contract T). */
export interface RateLimitOverrideRow {
  id: string;
  plan: string;
  policy: string;
  limit: number | null;
  window_seconds: number | null;
}

export function flattenRateLimitOverrides(
  overrides: RateLimitConfigOut["plan_overrides"],
): RateLimitOverrideRow[] {
  const rows: RateLimitOverrideRow[] = [];
  for (const [plan, policies] of Object.entries(overrides)) {
    for (const [policy, override] of Object.entries(policies)) {
      rows.push({
        id: `${plan}:${policy}`,
        plan,
        policy,
        limit: override.limit ?? null,
        window_seconds: override.window_seconds ?? null,
      });
    }
  }
  return rows;
}
