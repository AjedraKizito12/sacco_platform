import type { FetchClient } from "../client";

export function members(api: FetchClient) {
  return {
    list: (query?: Record<string, unknown>) =>
      api.GET("/members" as never, { params: { query } } as never),
    get: (id: string) =>
      api.GET("/members/{member_id}" as never, {
        params: { path: { member_id: id } },
      } as never),
    getKycRequirements: () => api.GET("/members/kyc-requirements" as never),
    putKycRequirements: (body: { required: Record<string, boolean> }) =>
      api.PUT("/members/kyc-requirements" as never, { body } as never),
    getKyc: (id: string) =>
      api.GET("/members/{member_id}/kyc" as never, {
        params: { path: { member_id: id } },
      } as never),
    listKycSubmissions: (query?: Record<string, unknown>) =>
      api.GET("/members/kyc-submissions" as never, { params: { query } } as never),
    getKycSubmission: (id: string) =>
      api.GET("/members/kyc-submissions/{submission_id}" as never, {
        params: { path: { submission_id: id } },
      } as never),
    approveKycSubmission: (id: string) =>
      api.POST("/members/kyc-submissions/{submission_id}/approve" as never, {
        params: { path: { submission_id: id } },
      } as never),
    rejectKycSubmission: (id: string, body: { reason: string }) =>
      api.POST("/members/kyc-submissions/{submission_id}/reject" as never, {
        params: { path: { submission_id: id } },
        body,
      } as never),
    create: (body: Record<string, unknown>) =>
      api.POST("/members" as never, { body } as never),
    changeStatus: (id: string, body: Record<string, unknown>) =>
      api.POST("/members/{member_id}/status-change" as never, {
        params: { path: { member_id: id } },
        body,
      } as never),
  } as const;
}
