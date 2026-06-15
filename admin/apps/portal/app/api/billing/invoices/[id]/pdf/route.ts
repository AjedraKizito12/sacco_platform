// admin/apps/portal/app/api/billing/invoices/[id]/pdf/route.ts
import { NextResponse } from "next/server";
import { getServerAccessToken } from "@/auth/server-helpers";

const API_BASE = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await params;
  const { accessToken } = await getServerAccessToken("platform");
  if (!accessToken) {
    return NextResponse.json({ error: "No platform session" }, { status: 401 });
  }

  const r = await fetch(`${API_BASE}/platform/billing/invoices/${id}.pdf`, {
    headers: { Authorization: `Bearer ${accessToken}` },
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
