"use client";

import {
  CommandPaletteTrigger,
  Header,
  NotificationBellStub,
  TenantIndicator,
  UserMenu,
} from "@sacco/ui";
import { useCurrentUser } from "@/auth/use-current-user";

interface AppShellHeaderProps {
  variant: "platform" | "tenant" | "member";
  tenantName?: string;
}

function PortalLogo() {
  return (
    <span className="text-[14px] font-semibold tracking-tight text-[var(--text-primary)]">
      SACCO
    </span>
  );
}

export function AppShellHeader({ variant, tenantName }: AppShellHeaderProps) {
  const user = useCurrentUser();

  async function onSignOut() {
    const endpoint =
      variant === "platform"
        ? "/api/auth/platform-logout"
        : variant === "member"
          ? "/api/auth/member-logout"
          : "/api/auth/tenant-logout";
    await fetch(endpoint, {
      method: "POST",
      credentials: "include",
    }).catch(() => {});
    const loginUrl =
      variant === "platform"
        ? "/platform/login"
        : variant === "member"
          ? "/member/login"
          : "/login";
    window.location.assign(loginUrl);
  }

  return (
    <Header
      logo={<PortalLogo />}
      start={
        (variant === "tenant" || variant === "member") && tenantName ? (
          <TenantIndicator tenantName={tenantName} />
        ) : null
      }
      center={
        variant === "member" ? null : (
          <CommandPaletteTrigger
            onActivate={() => {
              // Real palette ships in sub-plan 36
            }}
          />
        )
      }
      end={
        <>
          <NotificationBellStub />
          {user ? (
            <UserMenu
              fullName={user.full_name}
              email={user.email}
              contextLabel={
                variant === "member"
                  ? "Member"
                  : user.is_superuser
                    ? "Superuser"
                    : (user.role ?? "support").toUpperCase()
              }
              onSignOut={onSignOut}
            />
          ) : null}
        </>
      }
    />
  );
}
