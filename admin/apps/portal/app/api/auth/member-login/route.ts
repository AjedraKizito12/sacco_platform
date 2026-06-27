// admin/apps/portal/app/api/auth/member-login/route.ts
import { NextResponse } from "next/server";
import { loginSchema } from "@sacco/schemas";
import {
  MEMBER_REFRESH_COOKIE,
  MEMBER_REFRESH_MAX_AGE,
  getTenantSlugCookie,
  setRefreshCookie,
  setTenantSlugCookie,
} from "@/auth/cookies";

// Server-to-server: prefer the in-network host (Docker: http://api:8000),
// fall back to the public URL for local non-docker dev.
const API_BASE =
  process.env["API_INTERNAL_URL"] ??
  process.env["NEXT_PUBLIC_API_BASE_URL"] ??
  "http://localhost:8000";

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.json();
  const parsed = loginSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid request", issues: parsed.error.format() },
      { status: 400 },
    );
  }

  // The slug arrives as a header injected by middleware on page requests, but
  // middleware skips /api routes — so fall back to the sacco_tenant_slug cookie
  // (middleware persists it on first tenant-context resolution).
  const tenantSlug =
    request.headers.get("x-sacco-tenant-slug") ?? (await getTenantSlugCookie());
  if (!tenantSlug) {
    return NextResponse.json(
      { error: "Tenant context missing" },
      { status: 400 },
    );
  }

  const r = await fetch(`${API_BASE}/member/auth/token`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-Slug": tenantSlug,
    },
    body: JSON.stringify(parsed.data),
  });
  if (!r.ok) {
    const detail = await safeJson(r);
    return NextResponse.json(detail ?? { error: "Login failed" }, {
      status: r.status,
    });
  }
  const data = (await r.json()) as {
    access_token: string;
    refresh_token: string;
    expires_in: number;
  };

  await setRefreshCookie({
    name: MEMBER_REFRESH_COOKIE,
    value: data.refresh_token,
    maxAgeSeconds: MEMBER_REFRESH_MAX_AGE,
  });
  // Persist the slug so reloads keep tenant context without a query param.
  await setTenantSlugCookie(tenantSlug);

  return NextResponse.json({
    access_token: data.access_token,
    expires_in: data.expires_in,
    tenant_slug: tenantSlug,
  });
}

async function safeJson(r: Response): Promise<unknown> {
  try {
    return await r.json();
  } catch {
    return null;
  }
}
