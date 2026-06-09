"use client";

import type { TenantContext, TokenStore } from "@sacco/api-client";
import { create } from "zustand";

interface AuthState {
  accessToken: string | null;
  tenantSlug: string | null;
  authContext: "platform" | "tenant";
  setAccessToken(token: string | null): void;
  setTenantSlug(slug: string | null): void;
  setAuthContext(ctx: "platform" | "tenant"): void;
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
      : "/api/auth/tenant-refresh";
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
