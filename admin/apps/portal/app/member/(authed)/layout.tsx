import type { ReactNode } from "react";
import { redirect } from "next/navigation";
import { TenantCurrencyProvider } from "@sacco/ui";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import { AppShellHeader } from "@/components/AppShellHeader";
import { AppShellSidebar } from "@/components/AppShellSidebar";
import { AuthProvider } from "@/auth/AuthProvider";
import { PortalUserProvider } from "@/auth/portal-user-context";
import {
  getServerAccessToken,
  getServerCurrentUser,
  getServerTenantSlug,
} from "@/auth/server-helpers";

const API_BASE = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

export default async function MemberAuthedLayout({
  children,
}: {
  children: ReactNode;
}) {
  const slug = await getServerTenantSlug();
  if (!slug) redirect("/member/login");
  const { accessToken } = await getServerAccessToken("member");
  if (!accessToken) redirect("/member/login");
  const member = await getServerCurrentUser("member", accessToken);
  if (!member) redirect("/member/login");

  return (
    <AuthProvider
      baseUrl={API_BASE}
      initialAccessToken={accessToken}
      initialAuthContext="member"
      initialTenantSlug={slug}
      initialUser={member}
    >
      <PortalUserProvider user={member}>
        <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
          <AppErrorBoundary>
            <div className="flex min-h-screen flex-col">
              <div className="flex flex-1">
                <div className="flex w-full flex-col">
                  <AppShellHeader variant="member" tenantName={slug} />
                  <div className="flex flex-1">
                    <AppShellSidebar variant="member" />
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
