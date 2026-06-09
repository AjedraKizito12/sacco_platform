import createOpenapiFetch, { type Client as OpenapiClient } from "openapi-fetch";
import type { paths } from "./generated/schema";
import { authMiddleware } from "./middleware/auth";
import { tenantMiddleware } from "./middleware/tenant";
import { idempotencyMiddleware } from "./middleware/idempotency";
import { errorMiddleware } from "./middleware/errors";
import { refreshMiddleware } from "./middleware/refresh";
import type { TokenStore } from "./token-store";
import type { TenantContext } from "./tenant-context";

export interface ApiClientOptions {
  baseUrl: string;
  tokenStore: TokenStore;
  tenantContext: TenantContext;
  fetch?: typeof fetch;
}

export type FetchClient = OpenapiClient<paths>;

export function createApiClient(opts: ApiClientOptions): FetchClient {
  const client = createOpenapiFetch<paths>({
    baseUrl: opts.baseUrl,
    ...(opts.fetch !== undefined ? { fetch: opts.fetch } : {}),
  });

  // Middleware applies in declared order on request, reverse order on response.
  // Order: auth → tenant → idempotency → (server) → errors → refresh
  client.use(authMiddleware(opts.tokenStore));
  client.use(tenantMiddleware(opts.tenantContext));
  client.use(idempotencyMiddleware());
  client.use(errorMiddleware());
  client.use(refreshMiddleware(opts.tokenStore, opts.baseUrl));

  return client;
}
