"use client";

import {
  buildResources,
  createApiClient,
  type FetchClient,
  type Resources,
} from "@sacco/api-client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { CookieBackedTokenStore, ClientTenantContext, useAuthStore } from "./token-store";
import { useCurrentUserStore } from "./use-current-user";
import type { CurrentUserShape } from "./permissions";

interface AuthContextValue {
  api: FetchClient;
  resources: Resources;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

interface AuthProviderProps {
  children: ReactNode;
  baseUrl: string;
  initialAccessToken?: string | null;
  initialTenantSlug?: string | null;
  initialAuthContext?: "platform" | "tenant";
  initialUser?: CurrentUserShape | null;
}

export function AuthProvider({
  children,
  baseUrl,
  initialAccessToken,
  initialTenantSlug,
  initialAuthContext,
  initialUser,
}: AuthProviderProps) {
  // Hydrate the zustand stores once from server-provided values
  useEffect(() => {
    const store = useAuthStore.getState();
    if (initialAccessToken !== undefined) store.setAccessToken(initialAccessToken);
    if (initialTenantSlug !== undefined) store.setTenantSlug(initialTenantSlug);
    if (initialAuthContext) store.setAuthContext(initialAuthContext);
    if (initialUser !== undefined) {
      useCurrentUserStore.getState().setUser(initialUser);
    }
    // Intentionally no dep array — only run once at mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: (failureCount, error) => {
              // Never auto-retry on auth failure
              if (error instanceof Error && error.name === "UnauthorizedError") return false;
              return failureCount < 2;
            },
          },
        },
      }),
  );

  const value = useMemo<AuthContextValue>(() => {
    const api = createApiClient({
      baseUrl,
      tokenStore: new CookieBackedTokenStore(),
      tenantContext: new ClientTenantContext(),
    });
    return { api, resources: buildResources(api) };
  }, [baseUrl]);

  return (
    <AuthContext.Provider value={value}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </AuthContext.Provider>
  );
}
