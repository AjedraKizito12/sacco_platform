"use client";

import type { TenantContext, TokenStore } from "@sacco/api-client";
import { create } from "zustand";

type AuthContext = "platform" | "tenant" | "member";

interface AuthState {
  accessToken: string | null;
  tenantSlug: string | null;
  authContext: AuthContext;
  setAccessToken(token: string | null): void;
  setTenantSlug(slug: string | null): void;
  setAuthContext(ctx: AuthContext): void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  tenantSlug: null,
  authContext: "platform",
  setAccessToken: (token) => set({ accessToken: token }),
  setTenantSlug: (slug) => set({ tenantSlug: slug }),
  setAuthContext: (ctx) => set({ authContext: ctx }),
}));

export class CookieBackedTokenStore implements TokenStore {
  getAccessToken(): string | null {
    return useAuthStore.getState().accessToken;
  }
  setAccessToken(token: string | null): void {
    useAuthStore.getState().setAccessToken(token);
  }
  getRefreshEndpoint(): string {
    const ctx = useAuthStore.getState().authContext;
    return ctx === "platform"
      ? "/api/auth/platform-refresh"
      : ctx === "tenant"
        ? "/api/auth/tenant-refresh"
        : "/api/auth/member-refresh";
  }
  /**
   * Always returns null — refresh token lives in an httpOnly cookie. The
   * api-client's refresh middleware (sub-plan 05, amended in sub-plan 07
   * Task 1) sees null and uses credentials:include with no body.
   */
  getRefreshToken(): null {
    return null;
  }
}

export class ClientTenantContext implements TenantContext {
  getSlug(): string | null {
    return useAuthStore.getState().tenantSlug;
  }
}
