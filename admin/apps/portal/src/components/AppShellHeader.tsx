"use client";

import {
  CommandPaletteTrigger,
  Header,
  TenantIndicator,
  UserMenu,
} from "@sacco/ui";
import { useCurrentUser } from "@/auth/use-current-user";
import { AppShellNotificationBell } from "./AppShellNotificationBell";
import { AppShellThemeToggle } from "./AppShellThemeToggle";

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
          // Disabled until a real command palette / search backend is wired.
          // A live-looking search box that does nothing is worse than "coming soon".
          <CommandPaletteTrigger disabled onActivate={() => {}} />
        )
      }
      end={
        <>
          <AppShellThemeToggle />
          <AppShellNotificationBell variant={variant} />
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
