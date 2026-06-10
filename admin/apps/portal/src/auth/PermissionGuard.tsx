"use client";

import type { ReactNode } from "react";
import { userHasPermission } from "./permissions";
import { useCurrentUser } from "./use-current-user";

export interface PermissionGuardProps {
  permission: string;
  fallback?: ReactNode;
  children: ReactNode;
}

/**
 * Hides children when the current user lacks the permission. UX-only:
 * CLAUDE.md portal contract D says the API enforces; this exists so operators
 * don't see buttons they can't click.
 */
export function PermissionGuard({
  permission,
  fallback = null,
  children,
}: PermissionGuardProps) {
  const user = useCurrentUser();
  if (!userHasPermission(user, permission)) {
    return <>{fallback}</>;
  }
  return <>{children}</>;
}
