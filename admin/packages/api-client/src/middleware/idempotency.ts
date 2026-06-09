import type { Middleware } from "openapi-fetch";
import { v7 as uuidv7 } from "uuid";

const MUTATION_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/**
 * Auto-inject `Idempotency-Key` on mutating requests. Callers can override
 * by setting the header explicitly — useful when the same user intent
 * needs to share a key across retries.
 */
export function idempotencyMiddleware(): Middleware {
  return {
    async onRequest({ request }) {
      if (!MUTATION_METHODS.has(request.method)) {
        return request;
      }
      if (!request.headers.has("Idempotency-Key")) {
        request.headers.set("Idempotency-Key", uuidv7());
      }
      return request;
    },
  };
}
