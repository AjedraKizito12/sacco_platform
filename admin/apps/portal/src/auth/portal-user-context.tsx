"use client";

import { createContext, type ReactNode } from "react";
import type { CurrentUserShape } from "./permissions";

// `undefined` = not provided (consumers fall back to the client-side store).
// `null` = explicitly provided as "no user".
// `CurrentUserShape` = provided.
export const PortalUserContext = createContext<
  CurrentUserShape | null | undefined
>(undefined);

interface PortalUserProviderProps {
  user: CurrentUserShape | null;
  children: ReactNode;
}

/**
 * Provides the current portal user to PermissionGuard / useCurrentUser without
 * a render-cycle gap. Seeded by the server layout from the same /me response
 * that hydrates `useCurrentUserStore`; the context-first lookup means SSR
 * already knows the user, so the sidebar / user menu don't flash empty.
 */
export function PortalUserProvider({ user, children }: PortalUserProviderProps) {
  return (
    <PortalUserContext.Provider value={user}>
      {children}
    </PortalUserContext.Provider>
  );
}
