// admin/packages/api-client/src/client.ts
import createOpenapiFetch, { type Client as OpenapiClient } from "openapi-fetch";
import type { paths } from "./generated/schema";
import type { TokenStore } from "./token-store";
import type { TenantContext } from "./tenant-context";

export interface ApiClientOptions {
  baseUrl: string;
  tokenStore: TokenStore;
  tenantContext: TenantContext;
  /** Optional fetch override (tests inject MSW-aware fetch). */
  fetch?: typeof fetch;
}

export type FetchClient = OpenapiClient<paths>;

export function createApiClient(opts: ApiClientOptions): FetchClient {
  const client = createOpenapiFetch<paths>({
    baseUrl: opts.baseUrl,
    ...(opts.fetch !== undefined ? { fetch: opts.fetch } : {}),
  });
  // Middleware added in Task 4 — for now the client is a plain pass-through.
  // The opts.tokenStore and opts.tenantContext aren't yet consumed.
  void opts.tokenStore;
  void opts.tenantContext;
  return client;
}
