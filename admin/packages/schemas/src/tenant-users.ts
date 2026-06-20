import { z } from "zod";

// Mirrors app/platform_/tenant_users_admin/schemas.py.
export interface TenantUserOut {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_admin: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
  impersonation_id: string | null;
}

export const tenantUserCreateSchema = z.object({
  email: z.string().trim().toLowerCase().email("Enter a valid email address"),
  full_name: z.string().trim().min(1, "Full name is required").max(200),
  is_admin: z.boolean().default(false),
});
export type TenantUserCreateInput = z.infer<typeof tenantUserCreateSchema>;

export const tenantUserPatchSchema = z.object({
  full_name: z.string().trim().min(1, "Full name is required").max(200).optional(),
  is_active: z.boolean().optional(),
  is_admin: z.boolean().optional(),
});
export type TenantUserPatchInput = z.infer<typeof tenantUserPatchSchema>;

export function tenantUserRoleLabel(isAdmin: boolean): string {
  return isAdmin ? "Admin" : "Member";
}
