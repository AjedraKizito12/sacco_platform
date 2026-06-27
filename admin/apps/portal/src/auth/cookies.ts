import { cookies } from "next/headers";

export const PLATFORM_REFRESH_COOKIE = "sacco_refresh_platform";
export const TENANT_REFRESH_COOKIE = "sacco_refresh_tenant";
export const MEMBER_REFRESH_COOKIE = "sacco_refresh_member";
export const TENANT_SLUG_COOKIE = "sacco_tenant_slug";

const isProd = process.env.NODE_ENV === "production";

export const PLATFORM_REFRESH_MAX_AGE = 60 * 60; // 1 hour
export const TENANT_REFRESH_MAX_AGE = 60 * 60 * 8; // 8 hours
export const MEMBER_REFRESH_MAX_AGE = 60 * 60 * 8; // 8 hours

type RefreshCookieName =
  | typeof PLATFORM_REFRESH_COOKIE
  | typeof TENANT_REFRESH_COOKIE
  | typeof MEMBER_REFRESH_COOKIE;

interface SetRefreshArgs {
  name: RefreshCookieName;
  value: string;
  maxAgeSeconds: number;
}

export async function setRefreshCookie(args: SetRefreshArgs): Promise<void> {
  const jar = await cookies();
  jar.set({
    name: args.name,
    value: args.value,
    httpOnly: true,
    secure: isProd,
    sameSite: "strict",
    path: "/",
    maxAge: args.maxAgeSeconds,
  });
}

export async function clearRefreshCookie(
  name: RefreshCookieName,
): Promise<void> {
  const jar = await cookies();
  jar.delete(name);
}

export async function readRefreshCookie(
  name: RefreshCookieName,
): Promise<string | null> {
  const jar = await cookies();
  return jar.get(name)?.value ?? null;
}

export async function setTenantSlugCookie(slug: string): Promise<void> {
  const jar = await cookies();
  jar.set({
    name: TENANT_SLUG_COOKIE,
    value: slug,
    httpOnly: false, // readable by middleware AND client for the tenant indicator
    secure: isProd,
    sameSite: "strict",
    path: "/",
    maxAge: 60 * 60 * 24 * 30, // 30 days
  });
}

export async function clearTenantSlugCookie(): Promise<void> {
  const jar = await cookies();
  jar.delete(TENANT_SLUG_COOKIE);
}

export async function getTenantSlugCookie(): Promise<string | null> {
  const jar = await cookies();
  return jar.get(TENANT_SLUG_COOKIE)?.value ?? null;
}

export const IMPERSONATION_COOKIE = "sacco_impersonation";

export interface ImpersonationMarker {
  id: string;
  tenantId: string;
  tenantName: string;
  expiresAt: string;
}

// Marker that the operator is inside an impersonated tenant session. httpOnly
// so the tenant refresh token (set alongside it) is never exposed to client JS
// (contract C); read server-side in the (tenant-authed) layout to render the
// persistent banner.
export async function setImpersonationCookie(
  marker: ImpersonationMarker,
): Promise<void> {
  const jar = await cookies();
  jar.set(IMPERSONATION_COOKIE, JSON.stringify(marker), {
    httpOnly: true,
    secure: isProd,
    sameSite: "strict",
    path: "/",
    maxAge: TENANT_REFRESH_MAX_AGE,
  });
}

export async function readImpersonationCookie(): Promise<ImpersonationMarker | null> {
  const jar = await cookies();
  const raw = jar.get(IMPERSONATION_COOKIE)?.value;
  if (!raw) return null;
  try {
    return JSON.parse(raw) as ImpersonationMarker;
  } catch {
    return null;
  }
}

export async function clearImpersonationCookie(): Promise<void> {
  const jar = await cookies();
  jar.delete(IMPERSONATION_COOKIE);
}
