// admin/apps/portal/app/api/auth/member-logout/route.ts
import { NextResponse } from "next/server";
import { MEMBER_REFRESH_COOKIE, clearRefreshCookie } from "@/auth/cookies";

// Server-to-server: prefer the in-network host (Docker: http://api:8000),
// fall back to the public URL for local non-docker dev.
const API_BASE =
  process.env["API_INTERNAL_URL"] ??
  process.env["NEXT_PUBLIC_API_BASE_URL"] ??
  "http://localhost:8000";

export async function POST(request: Request): Promise<NextResponse> {
  // Best-effort: call backend logout if we have a Bearer header.
  const auth = request.headers.get("authorization");
  if (auth) {
    void fetch(`${API_BASE}/member/auth/logout`, {
      method: "POST",
      headers: { Authorization: auth },
    });
  }
  // Always clear our cookie even if the backend call fails.
  await clearRefreshCookie(MEMBER_REFRESH_COOKIE);
  return NextResponse.json({ status: "ok" });
}
