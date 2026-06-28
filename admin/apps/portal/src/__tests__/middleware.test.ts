import { describe, it, expect } from "vitest";
import { NextRequest } from "next/server";
import { middleware } from "../../middleware";

function req(path: string, cookies: Record<string, string> = {}): NextRequest {
  const url = `http://localhost${path}`;
  const cookieHeader = Object.entries(cookies)
    .map(([k, v]) => `${k}=${v}`)
    .join("; ");
  return new NextRequest(url, {
    headers: cookieHeader ? { cookie: cookieHeader } : {},
  });
}

function location(res: ReturnType<typeof middleware>): string | null {
  return res.headers.get("location");
}

describe("middleware /member vs /members prefix", () => {
  it("does NOT redirect the operator /members route to /member/login", () => {
    // Operator authenticated with the tenant refresh cookie.
    const res = middleware(
      req("/members", { sacco_refresh_tenant: "x", sacco_tenant_slug: "acme" }),
    );
    expect(location(res)).not.toBe("http://localhost/member/login");
  });

  it("redirects /members to operator /login when unauthenticated (not member login)", () => {
    const res = middleware(req("/members", { sacco_tenant_slug: "acme" }));
    expect(location(res)).toBe("http://localhost/login?next=%2Fmembers");
  });

  it("redirects an unauthenticated /member/* page to /member/login", () => {
    const res = middleware(
      req("/member/dashboard", { sacco_tenant_slug: "acme" }),
    );
    expect(location(res)).toBe(
      "http://localhost/member/login?next=%2Fmember%2Fdashboard",
    );
  });

  it("allows an authenticated /member/* page through", () => {
    const res = middleware(
      req("/member/dashboard", {
        sacco_refresh_member: "x",
        sacco_tenant_slug: "acme",
      }),
    );
    expect(location(res)).toBeNull();
  });
});
