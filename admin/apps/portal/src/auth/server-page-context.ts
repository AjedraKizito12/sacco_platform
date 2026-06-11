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
} from "./server-helpers";
import {
  type CurrentUserShape,
  userHasPermission,
} from "./permissions";

const API_BASE =
  process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

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
