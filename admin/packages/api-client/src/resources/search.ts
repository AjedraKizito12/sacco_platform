import type { FetchClient } from "../client";

export function search(api: FetchClient) {
  return {
    platformSearch: (q: string) =>
      api.GET("/platform/search" as never, {
        params: { query: { q } },
      } as never),
    tenantSearch: (q: string) =>
      api.GET("/search" as never, { params: { query: { q } } } as never),
  } as const;
}
