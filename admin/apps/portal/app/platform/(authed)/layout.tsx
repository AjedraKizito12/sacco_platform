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
} from "@/auth/server-helpers";

const API_BASE = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

export default async function PlatformAuthedLayout({
  children,
}: {
  children: ReactNode;
}) {
  const { accessToken } = await getServerAccessToken("platform");
  if (!accessToken) {
    redirect("/platform/login");
  }
  const user = await getServerCurrentUser("platform", accessToken);
  if (!user) {
    redirect("/platform/login");
  }
  return (
    <AuthProvider
      baseUrl={API_BASE}
      initialAccessToken={accessToken}
      initialAuthContext="platform"
      initialUser={user}
    >
      <PortalUserProvider user={user}>
        <TenantCurrencyProvider currency="UGX" timeZone="Africa/Kampala">
          <AppErrorBoundary>
            <div className="flex min-h-screen">
              <div className="flex w-full flex-col">
                <AppShellHeader variant="platform" />
                <div className="flex flex-1">
                  <AppShellSidebar variant="platform" />
                  <main className="mx-auto w-full max-w-[var(--width-content-max)] p-6">
                    {children}
                  </main>
                </div>
              </div>
            </div>
          </AppErrorBoundary>
        </TenantCurrencyProvider>
      </PortalUserProvider>
    </AuthProvider>
  );
}
