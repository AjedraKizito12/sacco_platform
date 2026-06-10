// Centralised permission registry. Until P1.7-05's 4-tier roles are fully
// consumable client-side, permissions resolve via a role table here. Each
// permission maps to a minimum role tier; superuser is an emergency back-door.

export class PermissionDeniedError extends Error {
  constructor(public readonly permission: string) {
    super(`Missing permission: ${permission}`);
    this.name = "PermissionDeniedError";
  }
}

/** Subset of the PlatformUser shape the portal needs for permission checks. */
export interface CurrentUserShape {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
  /** Phase 1.7-05 column. Defaults to "support" until set. */
  role?: "superuser" | "admin" | "finance" | "support";
}

const ROLE_RANK: Record<NonNullable<CurrentUserShape["role"]>, number> = {
  superuser: 4,
  admin: 3,
  finance: 2,
  support: 1,
};

export const PERMISSION_MIN_ROLE: Record<
  string,
  NonNullable<CurrentUserShape["role"]>
> = {
  // Platform admin
  "platform.users.read": "support",
  "platform.users.write": "superuser",
  "platform.tenants.read": "support",
  "platform.tenants.write": "admin",
  "platform.tenants.create": "superuser",
  "platform.tenants.suspend": "admin",
  // Billing
  "billing.read": "finance",
  "billing.write": "admin",
  // Approvals
  "approvals.read": "support",
  "approvals.approve": "admin",
  // Audit
  "audit.read": "admin",
  // Impersonation
  "impersonation.start": "support",
  "impersonation.revoke_other": "admin",
  // JWT keys
  "platform.security.jwt_keys.read": "superuser",
};

export function userHasPermission(
  user: CurrentUserShape | null,
  permission: string,
): boolean {
  if (!user) return false;
  if (user.is_superuser) return true;
  const required = PERMISSION_MIN_ROLE[permission];
  if (!required) return false;
  const userRole = user.role ?? "support";
  return (ROLE_RANK[userRole] ?? 0) >= ROLE_RANK[required];
}

/** Server-side helper — throws PermissionDeniedError when the user fails. */
export function requirePermission(
  user: CurrentUserShape | null,
  permission: string,
): asserts user is CurrentUserShape {
  if (!userHasPermission(user, permission)) {
    throw new PermissionDeniedError(permission);
  }
}
