"use client";

import {
  CommandPaletteTrigger,
  Header,
  TenantIndicator,
  UserMenu,
} from "@sacco/ui";
import { useEffect, useState } from "react";
import { useCurrentUser } from "@/auth/use-current-user";
import { AppShellCommandPalette } from "./AppShellCommandPalette";
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
  const [paletteOpen, setPaletteOpen] = useState(false);
  const searchVariant = variant === "platform" ? "platform" : "tenant";
  const hasSearch = variant !== "member";

  // Global ⌘K / Ctrl-K opens the palette (platform + operator only).
  useEffect(() => {
    if (!hasSearch) return;
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [hasSearch]);

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
        hasSearch ? (
          <CommandPaletteTrigger onActivate={() => setPaletteOpen(true)} />
        ) : null
      }
      end={
        <>
          {hasSearch ? (
            <AppShellCommandPalette
              variant={searchVariant}
              open={paletteOpen}
              onOpenChange={setPaletteOpen}
            />
          ) : null}
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
