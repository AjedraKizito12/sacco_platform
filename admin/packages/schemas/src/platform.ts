// admin/packages/schemas/src/platform.ts
import { z } from "zod";

export const platformRoleSchema = z.enum([
  "superuser",
  "admin",
  "finance",
  "support",
]);
export type PlatformRole = z.infer<typeof platformRoleSchema>;

/** Mirrors app/platform_/users/schemas.py CreatePlatformUserRequest.
 *  is_superuser is deprecated server-side (role is authoritative); the
 *  portal only sends role. */
export const createPlatformUserSchema = z.object({
  email: z.string().email("Enter a valid email address"),
  full_name: z.string().min(1, "Full name is required").max(200),
  role: platformRoleSchema.default("support"),
});
export type CreatePlatformUserInput = z.infer<typeof createPlatformUserSchema>;

/** Mirrors UpdatePlatformUserRequest. The portal always sends all three
 *  fields; the backend applies full_name immediately and routes is_active
 *  / role through maker-checker. */
export const updatePlatformUserSchema = z.object({
  full_name: z.string().min(1, "Full name is required").max(200),
  is_active: z.boolean(),
  role: platformRoleSchema,
});
export type UpdatePlatformUserInput = z.infer<typeof updatePlatformUserSchema>;

/** Mirrors PlatformUserOut. Dates are ISO strings over the wire. */
export interface PlatformUserOut {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
  role: PlatformRole;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}
