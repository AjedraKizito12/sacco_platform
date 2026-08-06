// admin/packages/schemas/src/tenants.ts
import { z } from "zod";

// Mirrors app/platform_/tenants/schemas.py _SLUG_RE. Slug is immutable
// after create.
export const TENANT_SLUG_RE = /^[a-z0-9-]{1,40}$/;

// Mirrors CreateTenantRequest. admin_email is optional server-side; the
// form models "not provided" as "" and the submit site strips it
// (conditional spread) so the wire payload omits the key entirely.
export const createTenantSchema = z.object({
  slug: z
    .string()
    .regex(TENANT_SLUG_RE, "Lowercase letters, digits and hyphens only (max 40)"),
  name: z.string().trim().min(1, "Name is required").max(200),
  admin_email: z
    .string()
    .trim()
    .toLowerCase()
    .email("Enter a valid email address")
    .or(z.literal("")),
});
export type CreateTenantInput = z.infer<typeof createTenantSchema>;

// Mirrors TenantOut. Dates are ISO strings over the wire.
export interface TenantOut {
  id: string;
  slug: string;
  schema_name: string;
  name: string;
  status: string;
  is_active: boolean;
  provisioning_state: string | null;
  failed_step: string | null;
  failure_reason: string | null;
  provisioning_started_at: string | null;
  provisioning_completed_at: string | null;
  seed_version: number;
  // Phase 7 — offboarding lifecycle + archival telemetry.
  lifecycle_state: string;
  cancelled_at: string | null;
  read_only_at: string | null;
  archived_at: string | null;
  hard_deleted_at: string | null;
  retention_hold_until: string | null;
  archive_storage_key: string | null;
  archive_size_bytes: number | null;
  archive_checksum: string | null;
  created_at: string;
  updated_at: string;
}

// Mirrors TenantLifecycleEventOut — one row of the offboarding timeline.
export interface TenantLifecycleEventOut {
  id: string;
  from_state: string;
  to_state: string;
  occurred_at: string;
  reason: string | null;
  actor_id: string | null;
  metadata: Record<string, unknown>;
}

// Mirrors TenantCancelIn — reason 10..500 chars (same shape as suspend).
export const tenantCancelSchema = z.object({
  reason: z
    .string()
    .trim()
    .min(10, "Give a reason of at least 10 characters")
    .max(500, "Reason must be 500 characters or fewer"),
});
export type TenantCancelInput = z.infer<typeof tenantCancelSchema>;

// Mirrors ExtendRetentionIn — an ISO timestamp for the new legal-hold date.
export const extendRetentionSchema = z.object({
  hold_until: z.string().min(1, "Choose a date"),
});
export type ExtendRetentionInput = z.infer<typeof extendRetentionSchema>;

/**
 * Derives a slug suggestion from a tenant name: lowercase, non-alphanumeric
 * runs collapsed to single hyphens, trimmed of edge hyphens, capped at 40.
 * Pure suggestion — the operator can always override; createTenantSchema is
 * the validator.
 */
export function suggestSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)
    .replace(/-+$/g, "");
}

// Mirrors TenantPatchIn — only name is editable; slug/schema are immutable.
export const tenantPatchSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200),
});
export type TenantPatchInput = z.infer<typeof tenantPatchSchema>;

// Mirrors TenantSuspendIn — reason 10..500 chars.
export const tenantSuspendSchema = z.object({
  reason: z
    .string()
    .trim()
    .min(10, "Give a reason of at least 10 characters")
    .max(500, "Reason must be 500 characters or fewer"),
});
export type TenantSuspendInput = z.infer<typeof tenantSuspendSchema>;

// Mirrors ImpersonationStartIn.reason — reason >= 10 chars. tenant_id is
// supplied by the screen, not the form.
export const impersonationRequestSchema = z.object({
  reason: z
    .string()
    .trim()
    .min(10, "Give a reason of at least 10 characters")
    .max(500, "Reason must be 500 characters or fewer"),
});
export type ImpersonationRequestInput = z.infer<typeof impersonationRequestSchema>;
