import type { Middleware } from "openapi-fetch";
import type { TokenStore } from "../token-store";
import { UnauthorizedError } from "../errors";

/**
 * 401-refresh-once. If a request 401s, we issue a single refresh call,
 * update the token store, and retry the original request once. If the
 * retry also 401s, we throw UnauthorizedError so the auth shell can
 * redirect to login.
 *
 * Concurrent 401s coalesce on the same in-flight promise — if 10 calls
 * all 401 in the same second, only one refresh call goes out.
 */
export function refreshMiddleware(
  tokenStore: TokenStore,
  baseUrl: string,
): Middleware {
  let pending: Promise<string | null> | null = null;

  async function refreshOnce(): Promise<string | null> {
    if (pending) return pending;
    pending = (async () => {
      try {
        const refreshToken = tokenStore.getRefreshToken();
        if (!refreshToken) return null;
        const r = await fetch(`${baseUrl}${tokenStore.getRefreshEndpoint()}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
          credentials: "include",
        });
        if (!r.ok) return null;
        const data = (await r.json()) as { access_token?: string };
        const token = data.access_token ?? null;
        tokenStore.setAccessToken(token);
        return token;
      } finally {
        pending = null;
      }
    })();
    return pending;
  }

  return {
    async onResponse({ request, response }) {
      if (response.status !== 401) return response;
      const newToken = await refreshOnce();
      if (!newToken) {
        throw new UnauthorizedError();
      }
      const retry = new Request(request, {
        headers: new Headers(request.headers),
      });
      retry.headers.set("Authorization", `Bearer ${newToken}`);
      const retryResponse = await fetch(retry);
      if (retryResponse.status === 401) {
        throw new UnauthorizedError();
      }
      return retryResponse;
    },
  };
}
