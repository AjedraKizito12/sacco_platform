import type { FetchClient } from "../client";

// Platform backup/restore operations (superuser). Mirrors app/platform_/ops/api.py.
export function ops(api: FetchClient) {
  return {
    getBackups: () => api.GET("/platform/ops/backups" as never),
    lastVerifiedAt: () =>
      api.GET("/platform/ops/backups/last-verified-at" as never),
    triggerVerification: () =>
      api.POST("/platform/ops/backups/trigger-verification" as never),
  } as const;
}
