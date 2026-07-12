import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Suspense, type ReactNode } from "react";

import { NuqsAdapter } from "nuqs/adapters/next/app";
import "./globals.css";
import { Toaster } from "@sacco/ui";
import { AuthProvider } from "@/auth/AuthProvider";
import { NavigationProgress } from "@/components/NavigationProgress";
import { getServerTenantSlug } from "@/auth/server-helpers";
import { getServerThemePrefs } from "@/theme/theme-cookie.server";
import { ThemeProvider } from "@/theme/ThemeProvider";
import { THEME_SCRIPT } from "@/theme/theme-script";

// Inter is the fallback in the design system's font stack
// (General Sans → Inter → system-ui). Sub-plan 04 swaps to a real
// General Sans @font-face declaration via Fontshare or self-hosted files.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: "SACCO Admin Portal",
  description: "Operational back-office for the SACCO platform",
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml" }],
  },
  robots: { index: false, follow: false },
};

const API_BASE = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8001";

export default async function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  const tenantSlug = await getServerTenantSlug();
  const initialAuthContext = tenantSlug ? "tenant" : "platform";
  const themePrefs = await getServerThemePrefs();
  const dataTheme = themePrefs.mode === "system" ? undefined : themePrefs.mode;
  return (
    <html
      lang="en"
      className={inter.variable}
      // The server intentionally omits `data-theme` for the default
      // "system" mode (it can't resolve the OS preference at request time),
      // while THEME_SCRIPT resolves it pre-paint on the client. That's an
      // expected, single-attribute mismatch on <html> — suppress it here
      // rather than suppressing hydration warnings tree-wide (standard
      // next-themes mitigation).
      suppressHydrationWarning
      {...(dataTheme ? { "data-theme": dataTheme } : {})}
      {...(themePrefs.accent !== "default" ? { "data-accent": themePrefs.accent } : {})}
      {...(themePrefs.fontSize !== "default" ? { "data-font-size": themePrefs.fontSize } : {})}
    >
      <head>
        {/*
          THEME_SCRIPT is a STATIC string constant with no interpolated user
          data — the one sanctioned use of dangerouslySetInnerHTML under
          contract E. It runs pre-paint to resolve "system" mode via
          matchMedia and stamp data-* attributes, eliminating a flash of the
          wrong theme.
        */}
        {/* eslint-disable-next-line react/no-danger -- THEME_SCRIPT is a static
            constant, no user data interpolated; sanctioned by contract E. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <Suspense fallback={null}>
          <NavigationProgress />
        </Suspense>
        <ThemeProvider initial={themePrefs}>
          <NuqsAdapter>
            <AuthProvider
              baseUrl={API_BASE}
              initialTenantSlug={tenantSlug}
              initialAuthContext={initialAuthContext}
            >
              {children}
            </AuthProvider>
          </NuqsAdapter>
        </ThemeProvider>
        <Toaster />
      </body>
    </html>
  );
}
