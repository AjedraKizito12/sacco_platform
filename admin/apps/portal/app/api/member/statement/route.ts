// admin/apps/portal/app/api/member/statement/route.ts
import { NextResponse } from "next/server";
import { getServerAccessToken, getServerTenantSlug } from "@/auth/server-helpers";

// Server-to-server: prefer the in-network host (Docker: http://api:8000),
// fall back to the public URL for local non-docker dev.
const API_BASE =
  process.env["API_INTERNAL_URL"] ??
  process.env["NEXT_PUBLIC_API_BASE_URL"] ??
  "http://localhost:8000";

export async function GET(request: Request): Promise<NextResponse> {
  const slug = await getServerTenantSlug();
  const { accessToken } = await getServerAccessToken("member");
  if (!slug || !accessToken) {
    return NextResponse.json({ error: "No member session" }, { status: 401 });
  }

  const incoming = new URL(request.url);
  const upstream = new URL(`${API_BASE}/member/statement`);
  for (const key of ["from_date", "to_date", "format"]) {
    const value = incoming.searchParams.get(key);
    if (value) upstream.searchParams.set(key, value);
  }

  const r = await fetch(upstream, {
    headers: { Authorization: `Bearer ${accessToken}`, "X-Tenant-Slug": slug },
    cache: "no-store",
  });
  if (!r.ok) {
    return NextResponse.json({ error: "Failed to load statement" }, { status: r.status });
  }
  const isHtml = (r.headers.get("content-type") ?? "").startsWith("text/html");
  const body = await r.arrayBuffer();
  return new NextResponse(body, {
    status: 200,
    headers: isHtml
      ? { "Content-Type": "text/html; charset=utf-8" }
      : {
          "Content-Type": "application/pdf",
          "Content-Disposition": 'attachment; filename="member-statement.pdf"',
        },
  });
}
