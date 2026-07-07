"use client";

import { useEffect, useState, type ReactNode } from "react";
import { AppShellHeader } from "./AppShellHeader";
import { AppShellSidebar } from "./AppShellSidebar";
import type { ShellVariant } from "./shell/nav-config";

interface AppShellProps {
  variant: ShellVariant;
  tenantName?: string;
  /** Wide-screen collapse preference, read from the cookie server-side. */
  initialCollapsed?: boolean;
  /** Optional banner rendered above the header (e.g. impersonation). */
  topBanner?: ReactNode;
  children: ReactNode;
}

const SMALL = "(max-width: 1023px)";

export function AppShell({
  variant,
  tenantName,
  initialCollapsed = false,
  topBanner,
  children,
}: AppShellProps) {
  const [collapsed, setCollapsed] = useState(initialCollapsed);
  const [isSmall, setIsSmall] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia(SMALL);
    const apply = () => setIsSmall(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  // Small screens force the icons-only rail; wide screens honour the toggle.
  const effectiveCollapsed = isSmall || collapsed;

  function toggle() {
    const next = !collapsed;
    setCollapsed(next);
    document.cookie = `sacco_sidebar_collapsed=${next ? "1" : "0"};path=/;max-age=${
      60 * 60 * 24 * 365
    };samesite=lax`;
  }

  return (
    <div className="flex min-h-screen flex-col">
      {topBanner}
      <AppShellHeader
        variant={variant}
        {...(tenantName !== undefined ? { tenantName } : {})}
      />
      <div className="flex flex-1">
        <AppShellSidebar
          variant={variant}
          collapsed={effectiveCollapsed}
          onToggle={toggle}
          canToggle={!isSmall}
        />
        <main className="mx-auto w-full max-w-[var(--width-content-max)] p-4 sm:p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
