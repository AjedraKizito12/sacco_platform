// Server-side helpers that read auth state from Next.js headers (set by
// middleware) and cookies. Used by server components to construct a
// per-request api-client.

import { headers } from "next/headers";

const HEADER_TENANT_SLUG = "x-sacco-tenant-slug";
const HEADER_ACCESS_TOKEN = "x-sacco-access-token";

export async function getServerTenantSlug(): Promise<string | null> {
  const h = await headers();
  return h.get(HEADER_TENANT_SLUG);
}

/**
 * The middleware does not mint access tokens — it forwards an existing
 * access token from a (short-lived, in-memory) cache. Server components
 * that need to issue authenticated calls must either:
 *   (a) read the access token from a per-request header set by the
 *       auth shell layout (sub-plan 08), or
 *   (b) call the refresh route handler to get a fresh token.
 *
 * Production wiring lands in sub-plan 08. For now, this helper returns
 * null and server-component calls fall back to the public surface.
 */
export async function getServerAccessToken(): Promise<string | null> {
  const h = await headers();
  return h.get(HEADER_ACCESS_TOKEN);
}
