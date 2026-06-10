"use client";

import { useContext } from "react";
import { create } from "zustand";
import type { CurrentUserShape } from "./permissions";
import { PortalUserContext } from "./portal-user-context";

interface UserState {
  user: CurrentUserShape | null;
  setUser(u: CurrentUserShape | null): void;
}

export const useCurrentUserStore = create<UserState>((set) => ({
  user: null,
  setUser: (u) => set({ user: u }),
}));

/**
 * Reads the current user from PortalUserContext when wrapped by the shell
 * layout, otherwise falls back to the zustand store. Consumers inside
 * `(authed)` / `(tenant-authed)` see the SSR-provided user without waiting
 * for the client-side hydration effect.
 */
export function useCurrentUser(): CurrentUserShape | null {
  const ctxUser = useContext(PortalUserContext);
  const storeUser = useCurrentUserStore((s) => s.user);
  return ctxUser !== undefined ? ctxUser : storeUser;
}
