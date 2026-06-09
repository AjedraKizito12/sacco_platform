import type { FetchClient } from "../client";

export function fees(api: FetchClient) {
  return {
    listTypes: (query?: Record<string, unknown>) =>
      api.GET("/fees/types" as never, { params: { query } } as never),
    createType: (body: Record<string, unknown>) =>
      api.POST("/fees/types" as never, { body } as never),
    getType: (id: string) =>
      api.GET("/fees/types/{fee_type_id}" as never, {
        params: { path: { fee_type_id: id } },
      } as never),
    patchType: (id: string, body: Record<string, unknown>) =>
      api.PATCH("/fees/types/{fee_type_id}" as never, {
        params: { path: { fee_type_id: id } },
        body,
      } as never),
    listAssessments: (query?: Record<string, unknown>) =>
      api.GET("/fees/assessments" as never, { params: { query } } as never),
    createAssessment: (body: Record<string, unknown>) =>
      api.POST("/fees/assessments" as never, { body } as never),
    getAssessment: (id: string) =>
      api.GET("/fees/assessments/{assessment_id}" as never, {
        params: { path: { assessment_id: id } },
      } as never),
    recordCollection: (body: Record<string, unknown>) =>
      api.POST("/fees/collections" as never, { body } as never),
  } as const;
}
