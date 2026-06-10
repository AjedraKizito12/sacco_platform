"use client";

import { useContext } from "react";
import { AuthContext } from "./AuthProvider";
import { useAuthStore } from "./token-store";

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  const accessToken = useAuthStore((s) => s.accessToken);
  const tenantSlug = useAuthStore((s) => s.tenantSlug);
  const authContext = useAuthStore((s) => s.authContext);
  return {
    ...ctx,
    accessToken,
    tenantSlug,
    authContext,
    isAuthenticated: accessToken !== null,
  };
}
