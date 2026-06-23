import { NextResponse } from "next/server";
import { getServerAccessToken } from "@/auth/server-helpers";
import {
  TENANT_REFRESH_COOKIE,
  clearImpersonationCookie,
  clearRefreshCookie,
  clearTenantSlugCookie,
} from "@/auth/cookies";

// Server-to-server: prefer the in-network host (Docker: http://api:8000),
// fall back to the public URL for local non-docker dev.
const API_BASE =
  process.env["API_INTERNAL_URL"] ??
  process.env["NEXT_PUBLIC_API_BASE_URL"] ??
  "http://localhost:8000";

export async function POST(request: Request): Promise<NextResponse> {
  const body = (await request.json()) as { impersonation_id?: string };
  if (!body.impersonation_id) {
    return NextResponse.json({ error: "Missing impersonation_id" }, { status: 400 });
  }

  const { accessToken } = await getServerAccessToken("platform");
  if (!accessToken) {
    return NextResponse.json({ error: "No platform session" }, { status: 401 });
  }

  // End the impersonation in platform context. Treat 404/410 (already
  // ended/expired) as success — the goal is to leave the tenant session.
  const r = await fetch(
    `${API_BASE}/platform/impersonations/${body.impersonation_id}`,
    {
      method: "DELETE",
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: "no-store",
    },
  );
  const ok = r.ok || r.status === 404 || r.status === 410;

  // Always clear the local tenant + impersonation cookies so the operator
  // returns to platform context regardless of the backend's terminal state.
  await clearRefreshCookie(TENANT_REFRESH_COOKIE);
  await clearTenantSlugCookie();
  await clearImpersonationCookie();

  if (!ok) {
    return NextResponse.json({ error: "End failed" }, { status: r.status });
  }
  return NextResponse.json({ ok: true });
}
