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

  const collapsed =
    (await cookies()).get("sacco_sidebar_collapsed")?.value === "1";

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
            <AppShell
              variant="member"
              tenantName={slug}
              initialCollapsed={collapsed}
            >
              {children}
            </AppShell>
          </AppErrorBoundary>
        </TenantCurrencyProvider>
      </PortalUserProvider>
    </AuthProvider>
  );
}
