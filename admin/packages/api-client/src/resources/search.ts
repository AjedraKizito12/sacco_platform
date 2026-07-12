import type { FetchClient } from "../client";

export function search(api: FetchClient) {
  return {
    platformSearch: (q: string, types?: string) =>
      api.GET("/platform/search" as never, {
        params: { query: types ? { q, types } : { q } },
      } as never),
    tenantSearch: (q: string, types?: string) =>
      api.GET("/search" as never, {
        params: { query: types ? { q, types } : { q } },
      } as never),
  } as const;
}
