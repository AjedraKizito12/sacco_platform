import { NextResponse } from "next/server";
import { getServerAccessToken } from "@/auth/server-helpers";
import {
  TENANT_REFRESH_COOKIE,
  TENANT_REFRESH_MAX_AGE,
  setImpersonationCookie,
  setRefreshCookie,
  setTenantSlugCookie,
} from "@/auth/cookies";

const API_BASE = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

interface ActivateBody {
  impersonation_id: string;
  tenant_id: string;
  tenant_name: string;
}

export async function POST(request: Request): Promise<NextResponse> {
  const body = (await request.json()) as Partial<ActivateBody>;
  if (!body.impersonation_id || !body.tenant_id || !body.tenant_name) {
    return NextResponse.json({ error: "Missing fields" }, { status: 400 });
  }

  const { accessToken } = await getServerAccessToken("platform");
  if (!accessToken) {
    return NextResponse.json({ error: "No platform session" }, { status: 401 });
  }

  const r = await fetch(
    `${API_BASE}/platform/impersonations/${body.impersonation_id}/mint-tenant-token`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: "no-store",
    },
  );
  if (!r.ok) {
    const detail = await safeJson(r);
    return NextResponse.json(detail ?? { error: "Mint failed" }, { status: r.status });
  }
  const data = (await r.json()) as {
    access_token: string;
    refresh_token: string;
    expires_in: number;
    tenant_slug: string;
    impersonation_id: string;
    impersonation_expires_at: string;
  };

  // Set the tenant refresh token httpOnly server-side (never in client JS).
  await setRefreshCookie({
    name: TENANT_REFRESH_COOKIE,
    value: data.refresh_token,
    maxAgeSeconds: TENANT_REFRESH_MAX_AGE,
  });
  await setTenantSlugCookie(data.tenant_slug);
  await setImpersonationCookie({
    id: data.impersonation_id,
    tenantId: body.tenant_id,
    tenantName: body.tenant_name,
    expiresAt: data.impersonation_expires_at,
  });

  return NextResponse.json({
    access_token: data.access_token,
    expires_in: data.expires_in,
    tenant_slug: data.tenant_slug,
  });
}

async function safeJson(r: Response): Promise<unknown> {
  try {
    return await r.json();
  } catch {
    return null;
  }
}
