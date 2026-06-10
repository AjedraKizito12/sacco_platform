// Resolves the active tenant slug for a request. Used by middleware AND
// by server-side helpers.
//
// Order of precedence (highest first):
//   1. Production: subdomain (e.g., sacco-one.app.sacco.example → "sacco-one")
//   2. Dev:        ?tenant=<slug> query param
//   3. Both:       sacco_tenant_slug cookie
//   4. null        (treat as platform-only context)
//
// The slug matches the backend's [a-z0-9-]{1,40} pattern.

const SLUG_RE = /^[a-z0-9-]{1,40}$/;

interface ResolveArgs {
  host: string | null;
  searchParams: URLSearchParams;
  cookieValue: string | null;
  rootDomain?: string; // e.g., "app.sacco.example"
}

export function resolveTenantSlug(args: ResolveArgs): string | null {
  // Subdomain in production
  if (args.host && args.rootDomain) {
    const subdomain = extractSubdomain(args.host, args.rootDomain);
    if (subdomain && SLUG_RE.test(subdomain)) return subdomain;
  }
  // Query param for dev
  const queryParam = args.searchParams.get("tenant");
  if (queryParam && SLUG_RE.test(queryParam)) return queryParam;
  // Cookie persistence
  if (args.cookieValue && SLUG_RE.test(args.cookieValue)) {
    return args.cookieValue;
  }
  return null;
}

function extractSubdomain(host: string, rootDomain: string): string | null {
  const hostNoPort = host.split(":")[0]?.toLowerCase() ?? "";
  const root = rootDomain.toLowerCase();
  if (hostNoPort === root || !hostNoPort.endsWith(`.${root}`)) return null;
  const sub = hostNoPort.slice(0, -1 - root.length);
  // Reject "www" and any nested-subdomain leftover dots.
  if (!sub || sub === "www" || sub.includes(".")) return null;
  return sub;
}
