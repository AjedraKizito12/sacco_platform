// Runs before every page request. Resolves tenant slug, propagates it to
// downstream server components via header, and redirects unauthenticated
// GETs of protected pages to the right login.

import { NextResponse, type NextRequest } from "next/server";
import { resolveTenantSlug } from "@/auth/tenant-resolver";

const PUBLIC_PATHS_PLATFORM = new Set([
  "/platform/login",
  "/platform/forgot-password",
  "/platform/reset-password",
]);
const PUBLIC_PATHS_TENANT = new Set([
  "/login",
  "/forgot-password",
  "/reset-password",
]);
const PUBLIC_PATHS_MEMBER = new Set([
  "/member/login",
  "/member/set-password",
  "/member/forgot-password",
  "/member/reset-password",
]);

const PLATFORM_REFRESH_COOKIE = "sacco_refresh_platform";
const TENANT_REFRESH_COOKIE = "sacco_refresh_tenant";
const MEMBER_REFRESH_COOKIE = "sacco_refresh_member";
const TENANT_SLUG_COOKIE = "sacco_tenant_slug";

const ROOT_DOMAIN = process.env["NEXT_PUBLIC_ROOT_DOMAIN"] ?? "";

export const config = {
  // Run on every request except Next.js internals and static assets.
  matcher: ["/((?!api|_next/static|_next/image|favicon|public).*)"],
};

export function middleware(request: NextRequest): NextResponse {
  const url = request.nextUrl;
  const pathname = url.pathname;

  const isPlatformPath = pathname.startsWith("/platform");
  const isMemberPath = pathname.startsWith("/member");

  // 1. Resolve tenant slug
  const slug = resolveTenantSlug({
    host: request.headers.get("host"),
    searchParams: url.searchParams,
    cookieValue: request.cookies.get(TENANT_SLUG_COOKIE)?.value ?? null,
    rootDomain: ROOT_DOMAIN,
  });

  // 2. Build request headers for downstream RSC consumption
  const headers = new Headers(request.headers);
  if (slug) headers.set("x-sacco-tenant-slug", slug);

  // 3. Authentication redirect. Member paths are checked first because
  // "/member/*" otherwise falls into the tenant namespace.
  const isPublic = isPlatformPath
    ? PUBLIC_PATHS_PLATFORM.has(pathname)
    : isMemberPath
      ? PUBLIC_PATHS_MEMBER.has(pathname)
      : PUBLIC_PATHS_TENANT.has(pathname);

  if (!isPublic) {
    const refreshCookie = isPlatformPath
      ? PLATFORM_REFRESH_COOKIE
      : isMemberPath
        ? MEMBER_REFRESH_COOKIE
        : TENANT_REFRESH_COOKIE;
    if (!request.cookies.has(refreshCookie)) {
      const loginPath = isPlatformPath
        ? "/platform/login"
        : isMemberPath
          ? "/member/login"
          : "/login";
      const redirect = new URL(loginPath, request.url);
      redirect.searchParams.set("next", pathname);
      return NextResponse.redirect(redirect);
    }
  }

  // 4. Persist tenant slug cookie on first-load query-param resolution (dev)
  const response = NextResponse.next({
    request: { headers },
  });
  if (slug && !request.cookies.has(TENANT_SLUG_COOKIE) && !isPlatformPath) {
    response.cookies.set({
      name: TENANT_SLUG_COOKIE,
      value: slug,
      httpOnly: false,
      secure: process.env["NODE_ENV"] === "production",
      sameSite: "strict",
      path: "/",
      maxAge: 60 * 60 * 24 * 30,
    });
  }
  return response;
}
