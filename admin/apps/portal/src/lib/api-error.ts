/**
 * Extracts a human-readable message from a failed api-client call.
 *
 * openapi-fetch resolves errors as the parsed FastAPI body, which carries a
 * `detail` string for 4xx responses. Typed errors thrown by the api-client
 * middleware (ServerError etc.) are real Error instances with a message.
 * Anything else falls back to the caller-supplied generic message.
 */
export function apiErrorMessage(err: unknown, fallback: string): string {
  if (typeof err === "object" && err !== null) {
    const detail = (err as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.length > 0) return detail;
    if (err instanceof Error && err.message) return err.message;
  }
  return fallback;
}
