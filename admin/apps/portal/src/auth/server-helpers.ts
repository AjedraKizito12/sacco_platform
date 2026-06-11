// Server-side helpers used by auth-protected layouts. They read the refresh
// cookie, perform a server-to-server refresh against FastAPI, and fetch /me
// — the result is then handed to <AuthProvider> for client hydration.
//
// Each helper is wrapped in React's `cache()` so that within a single server
// request the work is deduplicated: an authed layout and the page it wraps
// both resolve the access token + current user, but the refresh and /me round
// trips fire only once per request instead of twice. The platform/tenant
// refresh endpoints do NOT rotate the refresh token (the same session stays
// active), so this is purely an optimisation — behaviour is unchanged. React
// gives each request a fresh cache, so there is no cross-request leakage.

import { cache } from "react";
import { cookies, headers } from "next/headers";
import {
  PLATFORM_REFRESH_COOKIE,
  TENANT_REFRESH_COOKIE,
  TENANT_SLUG_COOKIE,
} from "./cookies";
import type { CurrentUserShape } from "./permissions";

const API_BASE = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";
const HEADER_TENANT_SLUG = "x-sacco-tenant-slug";

export const getServerTenantSlug = cache(
  async (): Promise<string | null> => {
    const h = await headers();
    const fromHeader = h.get(HEADER_TENANT_SLUG);
    if (fromHeader) return fromHeader;
    const jar = await cookies();
    return jar.get(TENANT_SLUG_COOKIE)?.value ?? null;
  },
);

/**
 * Server-to-server refresh. Reads the appropriate refresh cookie, calls the
 * FastAPI refresh endpoint directly, and returns the new access token.
 * Returns { accessToken: null } when there's no cookie or the backend rejects.
 *
 * Deduplicated per request via `cache()` — see the file header.
 */
export const getServerAccessToken = cache(
  async (
    variant: "platform" | "tenant",
  ): Promise<{ accessToken: string | null; expiresIn: number | null }> => {
    const jar = await cookies();
    const refreshCookieName =
      variant === "platform" ? PLATFORM_REFRESH_COOKIE : TENANT_REFRESH_COOKIE;
    const refreshToken = jar.get(refreshCookieName)?.value;
    if (!refreshToken) return { accessToken: null, expiresIn: null };

    const endpoint =
      variant === "platform" ? "/platform/auth/refresh" : "/auth/refresh";

    const headersInit: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (variant === "tenant") {
      const slug = await getServerTenantSlug();
      if (!slug) return { accessToken: null, expiresIn: null };
      headersInit["X-Tenant-Slug"] = slug;
    }

    const r = await fetch(`${API_BASE}${endpoint}`, {
      method: "POST",
      headers: headersInit,
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    });
    if (!r.ok) return { accessToken: null, expiresIn: null };
    const data = (await r.json()) as {
      access_token: string;
      expires_in: number;
    };
    return { accessToken: data.access_token, expiresIn: data.expires_in };
  },
);

/**
 * Calls /auth/me or /platform/auth/me with the provided access token and
 * returns the user shape. Returns null on any failure.
 *
 * Deduplicated per request via `cache()` — see the file header.
 */
export const getServerCurrentUser = cache(
  async (
    variant: "platform" | "tenant",
    accessToken: string,
  ): Promise<CurrentUserShape | null> => {
    const endpoint = variant === "platform" ? "/platform/auth/me" : "/auth/me";
    const headersInit: Record<string, string> = {
      Authorization: `Bearer ${accessToken}`,
    };
    if (variant === "tenant") {
      const slug = await getServerTenantSlug();
      if (slug) headersInit["X-Tenant-Slug"] = slug;
    }
    const r = await fetch(`${API_BASE}${endpoint}`, {
      headers: headersInit,
      cache: "no-store",
    });
    if (!r.ok) return null;
    return (await r.json()) as CurrentUserShape;
  },
);
