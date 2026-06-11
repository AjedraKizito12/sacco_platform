import type { Metadata } from "next";
import { Inter } from "next/font/google";
import type { ReactNode } from "react";

import "./globals.css";
import { Toaster } from "@sacco/ui";
import { AuthProvider } from "@/auth/AuthProvider";
import { getServerTenantSlug } from "@/auth/server-helpers";

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
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <AuthProvider
          baseUrl={API_BASE}
          initialTenantSlug={tenantSlug}
          initialAuthContext={initialAuthContext}
        >
          {children}
        </AuthProvider>
        <Toaster />
      </body>
    </html>
  );
}
