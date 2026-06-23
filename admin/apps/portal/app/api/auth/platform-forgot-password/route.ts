import { NextResponse } from "next/server";
import { passwordResetRequestSchema } from "@sacco/schemas";

// Server-to-server: prefer the in-network host (Docker: http://api:8000),
// fall back to the public URL for local non-docker dev.
const API_BASE =
  process.env["API_INTERNAL_URL"] ??
  process.env["NEXT_PUBLIC_API_BASE_URL"] ??
  "http://localhost:8000";

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.json();
  const parsed = passwordResetRequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid request" }, { status: 400 });
  }
  // Anti-enumeration: backend returns 204 regardless. We forward the status.
  const r = await fetch(`${API_BASE}/platform/auth/password-reset/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(parsed.data),
  });
  // 204 No Content: empty body, status pass-through.
  return new NextResponse(null, { status: r.status });
}
