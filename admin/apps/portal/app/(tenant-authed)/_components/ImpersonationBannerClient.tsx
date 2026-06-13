"use client";

import { useState } from "react";
import { ImpersonationBanner } from "@sacco/ui";

export function ImpersonationBannerClient({
  impersonationId,
  tenantId,
  tenantName,
  expiresAt,
}: {
  impersonationId: string;
  tenantId: string;
  tenantName: string;
  expiresAt: string;
}) {
  const [busy, setBusy] = useState(false);

  async function end() {
    setBusy(true);
    try {
      await fetch("/api/impersonation/end", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ impersonation_id: impersonationId }),
      });
    } finally {
      // Whether the call succeeded or not, the end route clears the tenant
      // cookies; return to the platform tenant detail.
      window.location.assign(`/platform/tenants/${tenantId}`);
    }
  }

  return (
    <ImpersonationBanner
      tenantName={tenantName}
      expiresAt={expiresAt}
      onEnd={() => void end()}
      busy={busy}
    />
  );
}
