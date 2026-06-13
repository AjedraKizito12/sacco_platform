import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { TenantCurrencyProvider } from "@sacco/ui";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import { AppShellHeader } from "@/components/AppShellHeader";
import { AppShellSidebar } from "@/components/AppShellSidebar";
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
            <div className="flex min-h-screen flex-col">
              {impersonation ? (
                <ImpersonationBannerClient
                  impersonationId={impersonation.id}
                  tenantId={impersonation.tenantId}
                  tenantName={impersonation.tenantName}
                  expiresAt={impersonation.expiresAt}
                />
              ) : null}
              <div className="flex flex-1">
                <div className="flex w-full flex-col">
                  <AppShellHeader variant="tenant" tenantName={slug} />
                  <div className="flex flex-1">
                    <AppShellSidebar variant="tenant" />
                    <main className="mx-auto w-full max-w-[var(--width-content-max)] p-6">
                      {children}
                    </main>
                  </div>
                </div>
              </div>
            </div>
          </AppErrorBoundary>
        </TenantCurrencyProvider>
      </PortalUserProvider>
    </AuthProvider>
  );
}
