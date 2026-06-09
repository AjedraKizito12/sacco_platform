import type { Middleware } from "openapi-fetch";
import type { TokenStore } from "../token-store";

export function authMiddleware(tokenStore: TokenStore): Middleware {
  return {
    async onRequest({ request }) {
      const token = tokenStore.getAccessToken();
      if (token) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
      return request;
    },
  };
}
