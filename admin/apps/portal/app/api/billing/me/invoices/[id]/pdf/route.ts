// admin/apps/portal/app/api/billing/me/invoices/[id]/pdf/route.ts
import { NextResponse } from "next/server";
import { getServerAccessToken, getServerTenantSlug } from "@/auth/server-helpers";

// Server-to-server: prefer the in-network host (Docker: http://api:8000),
// fall back to the public URL for local non-docker dev.
const API_BASE =
  process.env["API_INTERNAL_URL"] ??
  process.env["NEXT_PUBLIC_API_BASE_URL"] ??
  "http://localhost:8000";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await params;
  const slug = await getServerTenantSlug();
  const { accessToken } = await getServerAccessToken("tenant");
  if (!slug || !accessToken) {
    return NextResponse.json({ error: "No tenant session" }, { status: 401 });
  }

  const r = await fetch(`${API_BASE}/billing/me/invoices/${id}.pdf`, {
    headers: { Authorization: `Bearer ${accessToken}`, "X-Tenant-Slug": slug },
    cache: "no-store",
  });
  if (!r.ok) {
    return NextResponse.json({ error: "Failed to load invoice PDF" }, { status: r.status });
  }
  const body = await r.arrayBuffer();
  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `inline; filename="invoice-${id}.pdf"`,
    },
  });
}
