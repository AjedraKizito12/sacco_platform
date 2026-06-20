import type { FetchClient } from "../client";

export function keys(api: FetchClient) {
  return {
    listJwtKeys: () => api.GET("/platform/jwt-keys" as never, {} as never),
  } as const;
}
