// admin/apps/portal/app/api/auth/platform-login/route.ts
import { NextResponse } from "next/server";
import { loginSchema } from "@sacco/schemas";
import {
  PLATFORM_REFRESH_COOKIE,
  PLATFORM_REFRESH_MAX_AGE,
  setRefreshCookie,
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

  const r = await fetch(`${API_BASE}/platform/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
    name: PLATFORM_REFRESH_COOKIE,
    value: data.refresh_token,
    maxAgeSeconds: PLATFORM_REFRESH_MAX_AGE,
  });

  // Return the access token + expiry to the client; never the refresh token.
  return NextResponse.json({
    access_token: data.access_token,
    expires_in: data.expires_in,
  });
}

async function safeJson(r: Response): Promise<unknown> {
  try {
    return await r.json();
  } catch {
    return null;
  }
}
