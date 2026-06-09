// admin/packages/api-client/src/__tests__/setup.ts
// Vitest setup: patch tough-cookie so MSW can match handlers for URLs on
// reserved TLDs (like ".test"). Without this, tough-cookie v6 throws
// "Cookie has domain set to the public suffix" which MSW surfaces as an
// unhandled exception, causing the registered handler to never fire.
import { CookieJar } from "tough-cookie";

const original = CookieJar.prototype.getCookiesSync;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
CookieJar.prototype.getCookiesSync = function (url: string, opts?: any) {
  try {
    return original.call(this, url, opts);
  } catch {
    return [];
  }
};
