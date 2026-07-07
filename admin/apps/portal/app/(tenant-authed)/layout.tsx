import type { ReactNode } from "react";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { TenantCurrencyProvider } from "@sacco/ui";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import { AppShell } from "@/components/AppShell";
import { AuthProvider } from "@/auth/AuthProvider";
import { PortalUserProvider } from "@/auth/portal-user-context";
import { readImpersonationCookie } from "@/auth/cookies";
import {
  getServerAccessToken,
  getServerCurrentUser,
  getServerTenantSlug,
} from "@/auth/server-helpers";
import { ImpersonationBannerClient } from "./_components/ImpersonationBannerClient";

const API_BASE = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

export default async function TenantAuthedLayout({
  children,
}: {
  children: ReactNode;
}) {
  const slug = await getServerTenantSlug();
  if (!slug) redirect("/login");
  const { accessToken } = await getServerAccessToken("tenant");
  if (!accessToken) redirect("/login");
  const user = await getServerCurrentUser("tenant", accessToken);
  if (!user) redirect("/login");

  const impersonation = await readImpersonationCookie();
  const collapsed =
    (await cookies()).get("sacco_sidebar_collapsed")?.value === "1";

  return (
    <AuthProvider
      baseUrl={API_BASE}
      initialAccessToken={accessToken}
      initialAuthContext="tenant"
      initialTenantSlug={slug}
      initialUser={user}
    >
      <PortalUserProvider user={user}>
        <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
          <AppErrorBoundary>
            <AppShell
              variant="tenant"
              tenantName={slug}
              initialCollapsed={collapsed}
              topBanner={
                impersonation ? (
                  <ImpersonationBannerClient
                    impersonationId={impersonation.id}
                    tenantId={impersonation.tenantId}
                    tenantName={impersonation.tenantName}
                    expiresAt={impersonation.expiresAt}
                  />
                ) : null
              }
            >
              {children}
            </AppShell>
          </AppErrorBoundary>
        </TenantCurrencyProvider>
      </PortalUserProvider>
    </AuthProvider>
  );
}
