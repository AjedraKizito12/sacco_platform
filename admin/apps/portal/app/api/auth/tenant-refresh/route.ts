// admin/apps/portal/app/api/auth/tenant-refresh/route.ts
import { NextResponse } from "next/server";
import {
  TENANT_REFRESH_COOKIE,
  TENANT_REFRESH_MAX_AGE,
  readRefreshCookie,
  setRefreshCookie,
} from "@/auth/cookies";
import { cookies } from "next/headers";

const API_BASE = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

export async function POST(): Promise<NextResponse> {
  const refreshToken = await readRefreshCookie(TENANT_REFRESH_COOKIE);
  if (!refreshToken) {
    return NextResponse.json({ error: "No refresh token" }, { status: 401 });
  }
  // Tenant refresh needs the slug — read it from the persistence cookie.
  const jar = await cookies();
  const slug = jar.get("sacco_tenant_slug")?.value;
  if (!slug) {
    return NextResponse.json({ error: "Tenant context missing" }, { status: 401 });
  }
  const r = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-Slug": slug,
    },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!r.ok) {
    return NextResponse.json({ error: "Refresh failed" }, { status: 401 });
  }
  const data = (await r.json()) as {
    access_token: string;
    refresh_token: string;
    expires_in: number;
  };
  await setRefreshCookie({
    name: TENANT_REFRESH_COOKIE,
    value: data.refresh_token,
    maxAgeSeconds: TENANT_REFRESH_MAX_AGE,
  });
  return NextResponse.json({
    access_token: data.access_token,
    expires_in: data.expires_in,
  });
}
