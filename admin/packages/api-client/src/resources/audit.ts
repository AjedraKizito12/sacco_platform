import type { FetchClient } from "../client";

export function audit(_api: FetchClient) {
  // Audit log query API (P1.7-F) not yet merged.
  // Methods will be added once /platform/audit-log endpoints land.
  return {} as const;
}
