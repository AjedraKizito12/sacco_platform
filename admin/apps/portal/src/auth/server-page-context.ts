import { redirect } from "next/navigation";
import {
  buildResources,
  createApiClient,
  FixedTenantContext,
  InMemoryTokenStore,
  type Resources,
} from "@sacco/api-client";
import {
  getServerAccessToken,
  getServerCurrentUser,
  getServerTenantSlug,
} from "./server-helpers";
import {
  type CurrentUserShape,
  userHasPermission,
} from "./permissions";

// Server-to-server: prefer the in-network host (Docker: http://api:8000),
// fall back to the public URL for local non-docker dev.
const API_BASE =
  process.env["API_INTERNAL_URL"] ??
  process.env["NEXT_PUBLIC_API_BASE_URL"] ??
  "http://localhost:8000";

export interface PlatformPageContext {
  user: CurrentUserShape;
  resources: Resources;
}

/**
 * Server-component entrypoint for /platform/* pages: refreshes the access
 * token from the httpOnly cookie, fetches /me, and builds a per-request
 * typed api-client. Redirects to /platform/login when unauthenticated.
 *
 * A fresh InMemoryTokenStore per request avoids any cross-request token
 * bleed (server components run concurrently).
 */
export async function getPlatformPageContext(): Promise<PlatformPageContext> {
  const { accessToken } = await getServerAccessToken("platform");
  if (!accessToken) redirect("/platform/login");
  const user = await getServerCurrentUser("platform", accessToken);
  if (!user) redirect("/platform/login");

  const store = new InMemoryTokenStore("/platform/auth/refresh");
  store.setAccessToken(accessToken);
  const client = createApiClient({
    baseUrl: API_BASE,
    tokenStore: store,
    tenantContext: new FixedTenantContext(null),
  });
  return { user, resources: buildResources(client) };
}

export interface TenantPageContext {
  user: CurrentUserShape;
  slug: string;
  resources: Resources;
}

/**
 * Server-component entrypoint for (tenant-authed) pages. Mirrors
 * getPlatformPageContext but uses the tenant refresh cookie + slug so the
 * typed client sends X-Tenant-Slug on /billing/me/* calls. Redirects to
 * /login when unauthenticated.
 */
export async function getTenantPageContext(): Promise<TenantPageContext> {
  const slug = await getServerTenantSlug();
  const { accessToken } = await getServerAccessToken("tenant");
  if (!slug || !accessToken) redirect("/login");
  const user = await getServerCurrentUser("tenant", accessToken);
  if (!user) redirect("/login");

  const store = new InMemoryTokenStore("/auth/refresh");
  store.setAccessToken(accessToken);
  const client = createApiClient({
    baseUrl: API_BASE,
    tokenStore: store,
    tenantContext: new FixedTenantContext(slug),
  });
  return { user, slug, resources: buildResources(client) };
}

export interface MemberSelf {
  id: string;
  member_number: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  status: string;
  date_of_birth: string;
  gender: string;
  joined_at: string | null;
  last_login_at: string | null;
}

export interface MemberPageContext {
  member: MemberSelf;
  slug: string;
  resources: Resources;
}

/**
 * Server-component entrypoint for /member/(authed) pages. Mirrors
 * getTenantPageContext but uses the member refresh cookie + the
 * /member/auth/* endpoints. Redirects to /member/login when
 * unauthenticated. `getServerCurrentUser` returns `CurrentUserShape`;
 * the member /me shape differs, so we cast through `unknown` to
 * MemberSelf — the runtime payload is the 4a MemberOut.
 */
export async function getMemberPageContext(): Promise<MemberPageContext> {
  const slug = await getServerTenantSlug();
  const { accessToken } = await getServerAccessToken("member");
  if (!slug || !accessToken) redirect("/member/login");
  const member = (await getServerCurrentUser(
    "member",
    accessToken,
  )) as unknown as MemberSelf | null;
  if (!member) redirect("/member/login");

  const store = new InMemoryTokenStore("/member/auth/refresh");
  store.setAccessToken(accessToken);
  const client = createApiClient({
    baseUrl: API_BASE,
    tokenStore: store,
    tenantContext: new FixedTenantContext(slug),
  });
  return { member, slug, resources: buildResources(client) };
}

/**
 * UX-layer permission gate for server components. Redirects to the
 * permission-denied page when the user lacks `permission`. The API is the
 * real enforcement boundary (CLAUDE.md contract D); this only prevents a
 * data fetch + render for a user who would be rejected anyway.
 */
export function requirePlatformPermission(
  user: CurrentUserShape,
  permission: string,
): void {
  if (!userHasPermission(user, permission)) {
    redirect("/permission-denied");
  }
}
