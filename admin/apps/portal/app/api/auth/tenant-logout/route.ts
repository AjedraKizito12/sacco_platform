// admin/apps/portal/app/api/auth/tenant-logout/route.ts
import { NextResponse } from "next/server";
import {
  TENANT_REFRESH_COOKIE,
  clearRefreshCookie,
} from "@/auth/cookies";

const API_BASE = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

export async function POST(request: Request): Promise<NextResponse> {
  // Best-effort: call backend logout if we have a Bearer header.
  const auth = request.headers.get("authorization");
  if (auth) {
    void fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      headers: { Authorization: auth },
    });
  }
  // Always clear our cookie even if the backend call fails.
  await clearRefreshCookie(TENANT_REFRESH_COOKIE);
  return NextResponse.json({ status: "ok" });
}
