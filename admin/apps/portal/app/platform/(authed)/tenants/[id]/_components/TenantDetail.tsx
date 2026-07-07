"use client";

import type { ReactNode } from "react";
import {
  Card,
  FormattedDateTime,
  ReadOnlyField,
  StatusBadge,
} from "@sacco/ui";
import type { TenantOut } from "@sacco/schemas";
import { useTenantProvisioning } from "@/hooks/use-tenant-provisioning";
import { RetryProvisioningButton } from "./RetryProvisioningButton";
import { TenantActions } from "./TenantActions";

export function TenantDetail({
  tenant,
  canRetry,
  canImpersonate,
  canAssignPlan,
  canViewAudit,
  canManageUsers,
  auditBar,
  makerCheckerBanner,
  kycSection,
}: {
  tenant: TenantOut;
  canRetry: boolean;
  canImpersonate: boolean;
  canAssignPlan: boolean;
  canViewAudit: boolean;
  canManageUsers: boolean;
  auditBar: ReactNode;
  makerCheckerBanner: ReactNode;
  kycSection?: ReactNode;
}) {
  // Live-updates while the tenant is mid-provision; settles once terminal.
  const live = useTenantProvisioning(tenant.id, tenant);
  const t = live.data ?? tenant;

  return (
    <div className="flex flex-col gap-6">
      {makerCheckerBanner}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-[var(--text-h3)] font-semibold">{t.name}</h1>
          <StatusBadge entity="tenant" status={t.status} />
        </div>
        <div className="flex items-center gap-2">
          {canRetry && t.status === "failed" ? (
            <RetryProvisioningButton tenant={t} />
          ) : null}
          <TenantActions tenant={t} canWrite={canRetry} canImpersonate={canImpersonate} canAssignPlan={canAssignPlan} />
          {canManageUsers ? (
            <a
              href={`/platform/tenants/${t.id}/users`}
              className="text-[13px] text-[var(--text-link)]"
            >
              Users
            </a>
          ) : null}
          {canViewAudit ? (
            <a
              href={`/platform/tenants/${t.id}/audit`}
              className="text-[13px] text-[var(--text-link)]"
            >
              Audit log
            </a>
          ) : null}
        </div>
      </div>

      <Card className="grid grid-cols-2 gap-5 p-6">
        <ReadOnlyField label="Slug" value={t.slug} />
        <ReadOnlyField label="Schema" value={t.schema_name} />
        <ReadOnlyField label="Seed version" value={String(t.seed_version)} />
        <ReadOnlyField
          label="Created"
          value={<FormattedDateTime value={t.created_at} />}
        />
      </Card>

      <Card className="flex flex-col gap-4 p-6">
        <h2 className="text-[var(--text-h5)] font-semibold">Provisioning</h2>
        <div className="grid grid-cols-2 gap-5">
          <ReadOnlyField label="State" value={t.provisioning_state ?? "—"} />
          <ReadOnlyField
            label="Started"
            value={
              t.provisioning_started_at ? (
                <FormattedDateTime value={t.provisioning_started_at} />
              ) : (
                "—"
              )
            }
          />
          <ReadOnlyField
            label="Completed"
            value={
              t.provisioning_completed_at ? (
                <FormattedDateTime value={t.provisioning_completed_at} />
              ) : (
                "—"
              )
            }
          />
          {t.status === "failed" ? (
            <ReadOnlyField label="Failed step" value={t.failed_step ?? "unknown"} />
          ) : null}
        </div>
        {t.status === "failed" && t.failure_reason ? (
          <p className="text-[var(--text-danger)]">{t.failure_reason}</p>
        ) : null}
      </Card>

      {kycSection}

      {auditBar}
    </div>
  );
}
