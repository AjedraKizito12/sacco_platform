"use client";

import { useContext, type ReactNode } from "react";
import { userHasPermission } from "./permissions";
import { PortalUserContext } from "./portal-user-context";
import { useCurrentUserStore } from "./use-current-user";

export interface PermissionGuardProps {
  permission: string;
  fallback?: ReactNode;
  children: ReactNode;
}

/**
 * Hides children when the current user lacks the permission. UX-only:
 * CLAUDE.md portal contract D says the API enforces; this exists so operators
 * don't see buttons they can't click.
 *
 * Prefers PortalUserContext over the zustand store so SSR-rendered guards
 * (the AppShellSidebar in particular) reflect the real user instead of
 * flashing an empty state before client hydration.
 */
export function PermissionGuard({
  permission,
  fallback = null,
  children,
}: PermissionGuardProps) {
  const ctxUser = useContext(PortalUserContext);
  const storeUser = useCurrentUserStore((s) => s.user);
  const user = ctxUser !== undefined ? ctxUser : storeUser;
  if (!userHasPermission(user, permission)) {
    return <>{fallback}</>;
  }
  return <>{children}</>;
}
