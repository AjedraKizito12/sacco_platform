"use client";

import { create } from "zustand";
import type { CurrentUserShape } from "./permissions";

interface UserState {
  user: CurrentUserShape | null;
  setUser(u: CurrentUserShape | null): void;
}

export const useCurrentUserStore = create<UserState>((set) => ({
  user: null,
  setUser: (u) => set({ user: u }),
}));

export function useCurrentUser(): CurrentUserShape | null {
  return useCurrentUserStore((s) => s.user);
}
