import type { Middleware } from "openapi-fetch";
import type { TenantContext } from "../tenant-context";

export function tenantMiddleware(tenantContext: TenantContext): Middleware {
  return {
    async onRequest({ request }) {
      const slug = tenantContext.getSlug();
      const url = new URL(request.url);
      const needsSlug =
        !url.pathname.startsWith("/platform/") &&
        !url.pathname.startsWith("/.well-known/") &&
        slug !== null;
      if (needsSlug) {
        request.headers.set("X-Tenant-Slug", slug);
      }
      return request;
    },
  };
}
