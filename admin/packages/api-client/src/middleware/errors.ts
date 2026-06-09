import type { Middleware } from "openapi-fetch";
import {
  ServerError,
  SubscriptionPastDueError,
  SubscriptionSuspendedError,
} from "../errors";

const GATE_403_PREFIX = "Subscription status";

export function errorMiddleware(): Middleware {
  return {
    async onResponse({ response }) {
      if (response.ok) return response;

      const status = response.status;

      if (status === 402) {
        const body = await safeJson(response);
        const detail402 = body?.["detail"];
        throw new SubscriptionPastDueError(
          typeof detail402 === "string" ? detail402 : "Subscription past due",
        );
      }

      if (status === 403) {
        const body = await safeJson(response);
        const detail403 = body?.["detail"];
        if (
          typeof detail403 === "string" &&
          detail403.startsWith(GATE_403_PREFIX)
        ) {
          throw new SubscriptionSuspendedError(detail403);
        }
      }

      if (status >= 500) {
        const requestId = response.headers.get("X-Request-ID");
        const body = await safeJson(response);
        const detail5xx = body?.["detail"];
        throw new ServerError(
          status,
          requestId,
          typeof detail5xx === "string" ? detail5xx : undefined,
        );
      }

      return response;
    },
  };
}

async function safeJson(response: Response): Promise<Record<string, unknown> | null> {
  try {
    return (await response.clone().json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}
