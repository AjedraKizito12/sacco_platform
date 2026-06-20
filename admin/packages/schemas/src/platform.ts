// admin/packages/schemas/src/platform.ts
import { z } from "zod";

export const platformRoleSchema = z.enum([
  "superuser",
  "admin",
  "finance",
  "support",
]);
export type PlatformRole = z.infer<typeof platformRoleSchema>;

export const PLATFORM_ROLE_LABELS: Record<PlatformRole, string> = {
  superuser: "Superuser",
  admin: "Admin",
  finance: "Finance",
  support: "Support",
};

/** Display order for role pickers: least-privileged first. */
export const PLATFORM_ROLE_OPTIONS: { value: PlatformRole; label: string }[] = [
  { value: "support", label: PLATFORM_ROLE_LABELS.support },
  { value: "finance", label: PLATFORM_ROLE_LABELS.finance },
  { value: "admin", label: PLATFORM_ROLE_LABELS.admin },
  { value: "superuser", label: PLATFORM_ROLE_LABELS.superuser },
];

// Mirrors app/platform_/users/schemas.py CreatePlatformUserRequest.
// is_superuser is deprecated server-side (role is authoritative); the
// portal only sends role.
export const createPlatformUserSchema = z.object({
  email: z.string().trim().toLowerCase().email("Enter a valid email address"),
  full_name: z.string().trim().min(1, "Full name is required").max(200),
  role: platformRoleSchema.default("support"),
});
export type CreatePlatformUserInput = z.infer<typeof createPlatformUserSchema>;

// Does NOT mirror UpdatePlatformUserRequest exactly — backend makes all three
// fields optional; portal always sends them together. full_name is applied
// immediately; is_active / role are routed through maker-checker.
export const updatePlatformUserSchema = z.object({
  full_name: z.string().trim().min(1, "Full name is required").max(200),
  is_active: z.boolean(),
  role: platformRoleSchema,
});
export type UpdatePlatformUserInput = z.infer<typeof updatePlatformUserSchema>;

// Mirrors PlatformUserOut. Dates are ISO strings over the wire.
export interface PlatformUserOut {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  /** @deprecated mirror of role; use role */
  is_superuser: boolean;
  role: PlatformRole;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}

// Mirrors app/platform_/admin/schemas.py DashboardStatsOut. Decimal fields
// arrive as JSON strings (FastAPI serialises Decimal as a string), so the
// per-currency maps are Record<string, string> — the same shape <Money> reads.
export interface DashboardStatsOut {
  tenants: Record<string, number>;
  subscriptions: Record<string, number>;
  mrr: Record<string, string>;
  invoices_outstanding: Record<string, number>;
  invoices_amount_outstanding: Record<string, string>;
  approvals_pending: number;
  active_impersonations: number;
  last_updated: string;
}
