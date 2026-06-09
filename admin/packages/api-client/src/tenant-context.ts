// admin/packages/api-client/src/tenant-context.ts
/**
 * Supplies the current tenant slug for tenant-scoped requests. In platform
 * context, getSlug() returns null and tenantMiddleware skips header
 * injection (the request is going to /platform/* which doesn't need it).
 */
export interface TenantContext {
  getSlug(): string | null;
}

export class FixedTenantContext implements TenantContext {
  #slug: string | null;
  constructor(slug: string | null) {
    this.#slug = slug;
  }
  getSlug(): string | null {
    return this.#slug;
  }
}
