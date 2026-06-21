// admin/apps/portal/app/api/reporting/[report]/route.ts
import { NextResponse } from "next/server";
import { getServerAccessToken, getServerTenantSlug } from "@/auth/server-helpers";

const API_BASE = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

const ALLOWED = new Set([
  "trial-balance",
  "loan-portfolio",
  "income-statement",
  "savings-statement",
  "fee-collection",
]);

export async function GET(
  request: Request,
  { params }: { params: Promise<{ report: string }> },
): Promise<NextResponse> {
  const { report } = await params;
  if (!ALLOWED.has(report)) {
    return NextResponse.json({ error: "Unknown report" }, { status: 404 });
  }
  const slug = await getServerTenantSlug();
  const { accessToken } = await getServerAccessToken("tenant");
  if (!slug || !accessToken) {
    return NextResponse.json({ error: "No tenant session" }, { status: 401 });
  }

  const incoming = new URL(request.url);
  const qs = incoming.searchParams.toString();
  const upstream = `${API_BASE}/reporting/${report}${qs ? `?${qs}` : ""}`;

  const r = await fetch(upstream, {
    headers: { Authorization: `Bearer ${accessToken}`, "X-Tenant-Slug": slug },
    cache: "no-store",
  });
  if (!r.ok) {
    return NextResponse.json({ error: "Failed to load report" }, { status: r.status });
  }
  const body = await r.arrayBuffer();
  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": r.headers.get("content-type") ?? "application/octet-stream",
      "Content-Disposition":
        r.headers.get("content-disposition") ?? `attachment; filename="${report}"`,
    },
  });
}
