// admin/packages/api-client/src/token-store.ts
/**
 * Token store contract: the auth shell (sub-plan 07) supplies the
 * implementation; the api-client uses it transparently. Server components
 * may inject a per-request store; client components share a single one.
 */
export interface TokenStore {
  /** Returns the current access token, or null if unauthenticated. */
  getAccessToken(): string | null;
  /** Persists a refreshed access token. Called by refreshMiddleware. */
  setAccessToken(token: string | null): void;
  /**
   * Returns the refresh-endpoint path for the current auth context.
   * `/platform/auth/refresh` for platform context, `/auth/refresh` for
   * tenant context.
   */
  getRefreshEndpoint(): "/platform/auth/refresh" | "/auth/refresh";
  /**
   * Returns the current refresh token. May return null in server context
   * where the token is in an httpOnly cookie and Next.js forwards it via
   * the same-origin fetch.
   */
  getRefreshToken(): string | null;
}

export class InMemoryTokenStore implements TokenStore {
  #accessToken: string | null = null;
  #refreshToken: string | null = null;
  #refreshEndpoint: "/platform/auth/refresh" | "/auth/refresh";

  constructor(
    refreshEndpoint: "/platform/auth/refresh" | "/auth/refresh",
  ) {
    this.#refreshEndpoint = refreshEndpoint;
  }

  getAccessToken(): string | null {
    return this.#accessToken;
  }
  setAccessToken(token: string | null): void {
    this.#accessToken = token;
  }
  getRefreshEndpoint(): "/platform/auth/refresh" | "/auth/refresh" {
    return this.#refreshEndpoint;
  }
  getRefreshToken(): string | null {
    return this.#refreshToken;
  }
  setRefreshToken(token: string | null): void {
    this.#refreshToken = token;
  }
}
