// admin/packages/schemas/src/notifications.ts
// Mirrors app/core/notifications/{schemas,catalog}.py. Adding an event code =
// backend catalog row + template seed + ONE row here (status-maps pattern).
import { z } from "zod";

export type NotificationAudience = "platform" | "tenant" | "member";
export type NotificationChannel = "email" | "in_app";

export interface NotificationCatalogRow {
  code: string;
  label: string;
  audiences: NotificationAudience[];
  channels: NotificationChannel[];
}

const STAFF: NotificationAudience[] = ["platform", "tenant"];
const ALL: NotificationAudience[] = ["platform", "tenant", "member"];
const MEMBER: NotificationAudience[] = ["member"];
const TENANT: NotificationAudience[] = ["tenant"];
const BOTH: NotificationChannel[] = ["email", "in_app"];

export const PORTAL_NOTIFICATION_CATALOG: readonly NotificationCatalogRow[] = [
  { code: "password_reset", label: "Password reset requested", audiences: ALL, channels: BOTH },
  { code: "maker_checker_pending", label: "Approval requests awaiting review", audiences: STAFF, channels: BOTH },
  { code: "maker_checker_approved", label: "Your requests approved", audiences: STAFF, channels: BOTH },
  { code: "maker_checker_rejected", label: "Your requests rejected", audiences: STAFF, channels: BOTH },
  { code: "invoice_issued", label: "Invoice issued", audiences: TENANT, channels: BOTH },
  { code: "invoice_overdue", label: "Invoice overdue", audiences: TENANT, channels: BOTH },
  { code: "subscription_suspended", label: "Subscription suspended", audiences: TENANT, channels: BOTH },
  { code: "system_announcement", label: "System announcements", audiences: ALL, channels: BOTH },
  { code: "member_activated", label: "Membership activated", audiences: MEMBER, channels: BOTH },
  { code: "kyc_submission_approved", label: "KYC approved", audiences: MEMBER, channels: BOTH },
  { code: "kyc_submission_rejected", label: "KYC needs changes", audiences: MEMBER, channels: BOTH },
  { code: "loan_application_approved", label: "Loan application approved", audiences: MEMBER, channels: BOTH },
  { code: "loan_application_rejected", label: "Loan application declined", audiences: MEMBER, channels: BOTH },
];

export function catalogForAudience(
  audience: NotificationAudience,
): NotificationCatalogRow[] {
  return PORTAL_NOTIFICATION_CATALOG.filter((row) =>
    row.audiences.includes(audience),
  );
}

// ── Wire types (mirror app/core/notifications/schemas.py) ────────────────────

export interface NotificationFeedItemOut {
  id: string;
  event_code: string;
  title: string;
  body: string;
  status: string;
  created_at: string;
  read_at: string | null;
}

export interface NotificationPreferenceOut {
  event_code: string;
  channel: string;
  enabled: boolean;
}

export interface NotificationTemplateOut {
  id: string;
  code: string;
  channel: string;
  locale: string;
  subject_template: string | null;
  body_html: string | null;
  body_text: string | null;
  sms_body: string | null;
  variables: Record<string, string>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface NotificationEventAdminOut {
  id: string;
  event_code: string;
  recipient_kind: string;
  recipient_user_id: string;
  recipient_email: string | null;
  channels: string[];
  context: Record<string, unknown>;
  scheduled_at: string;
  status: string;
  created_at: string;
}

// ── Forms ─────────────────────────────────────────────────────────────────────

export const notificationTemplatePatchSchema = z.object({
  subject_template: z.string().optional(),
  body_text: z.string().optional(),
  body_html: z.string().optional(),
  sms_body: z.string().optional(),
  is_active: z.boolean().optional(),
});

export type NotificationTemplatePatchInput = z.infer<
  typeof notificationTemplatePatchSchema
>;
