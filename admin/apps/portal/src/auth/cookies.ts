import { cookies } from "next/headers";

export const PLATFORM_REFRESH_COOKIE = "sacco_refresh_platform";
export const TENANT_REFRESH_COOKIE = "sacco_refresh_tenant";
export const TENANT_SLUG_COOKIE = "sacco_tenant_slug";

const isProd = process.env.NODE_ENV === "production";

export const PLATFORM_REFRESH_MAX_AGE = 60 * 60; // 1 hour
export const TENANT_REFRESH_MAX_AGE = 60 * 60 * 8; // 8 hours

interface SetRefreshArgs {
  name: typeof PLATFORM_REFRESH_COOKIE | typeof TENANT_REFRESH_COOKIE;
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
  name: typeof PLATFORM_REFRESH_COOKIE | typeof TENANT_REFRESH_COOKIE,
): Promise<void> {
  const jar = await cookies();
  jar.delete(name);
}

export async function readRefreshCookie(
  name: typeof PLATFORM_REFRESH_COOKIE | typeof TENANT_REFRESH_COOKIE,
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
