// admin/packages/schemas/src/platform.ts
import { z } from "zod";

export const platformRoleSchema = z.enum([
  "superuser",
  "admin",
  "finance",
  "support",
]);
export type PlatformRole = z.infer<typeof platformRoleSchema>;

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
