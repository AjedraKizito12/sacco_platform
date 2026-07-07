import type { FetchClient } from "../client";

export function organization(api: FetchClient) {
  return {
    getKyc: () => api.GET("/organization/kyc" as never),
    putKyc: (body: Record<string, string | null>) =>
      api.PUT("/organization/kyc" as never, { body } as never),
  } as const;
}
