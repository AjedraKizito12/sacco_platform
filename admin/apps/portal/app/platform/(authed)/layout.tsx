import type { ReactNode } from "react";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { TenantCurrencyProvider } from "@sacco/ui";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import { AppShell } from "@/components/AppShell";
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
  const collapsed =
    (await cookies()).get("sacco_sidebar_collapsed")?.value === "1";
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
            <AppShell variant="platform" initialCollapsed={collapsed}>
              {children}
            </AppShell>
          </AppErrorBoundary>
        </TenantCurrencyProvider>
      </PortalUserProvider>
    </AuthProvider>
  );
}
