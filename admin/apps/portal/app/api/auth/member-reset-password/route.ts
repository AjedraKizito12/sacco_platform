import { NextResponse } from "next/server";
import { passwordResetConfirmSchema } from "@sacco/schemas";

// Server-to-server: prefer the in-network host (Docker: http://api:8000),
// fall back to the public URL for local non-docker dev.
const API_BASE =
  process.env["API_INTERNAL_URL"] ??
  process.env["NEXT_PUBLIC_API_BASE_URL"] ??
  "http://localhost:8000";

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.json();
  const parsed = passwordResetConfirmSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid request" }, { status: 400 });
  }

  const tenantSlug = request.headers.get("x-sacco-tenant-slug");
  if (!tenantSlug) {
    return NextResponse.json(
      { error: "Tenant context missing" },
      { status: 400 },
    );
  }

  const r = await fetch(`${API_BASE}/member/auth/password-reset/confirm`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Tenant-Slug": tenantSlug,
    },
    body: JSON.stringify({
      token: parsed.data.token,
      new_password: parsed.data.new_password,
    }),
  });

  if (r.status === 204) return new NextResponse(null, { status: 204 });
  const detail = await r.json().catch(() => ({ detail: "Reset failed" }));
  return NextResponse.json(detail, { status: r.status });
}
