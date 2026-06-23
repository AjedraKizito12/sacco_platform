// admin/apps/portal/app/api/auth/platform-refresh/route.ts
import { NextResponse } from "next/server";
import {
  PLATFORM_REFRESH_COOKIE,
  PLATFORM_REFRESH_MAX_AGE,
  readRefreshCookie,
  setRefreshCookie,
} from "@/auth/cookies";

// Server-to-server: prefer the in-network host (Docker: http://api:8000),
// fall back to the public URL for local non-docker dev.
const API_BASE =
  process.env["API_INTERNAL_URL"] ??
  process.env["NEXT_PUBLIC_API_BASE_URL"] ??
  "http://localhost:8000";

export async function POST(): Promise<NextResponse> {
  const refreshToken = await readRefreshCookie(PLATFORM_REFRESH_COOKIE);
  if (!refreshToken) {
    return NextResponse.json({ error: "No refresh token" }, { status: 401 });
  }
  const r = await fetch(`${API_BASE}/platform/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
    name: PLATFORM_REFRESH_COOKIE,
    value: data.refresh_token,
    maxAgeSeconds: PLATFORM_REFRESH_MAX_AGE,
  });
  return NextResponse.json({
    access_token: data.access_token,
    expires_in: data.expires_in,
  });
}
