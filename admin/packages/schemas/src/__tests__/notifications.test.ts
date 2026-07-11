import { describe, expect, it } from "vitest";
import {
  catalogForAudience,
  notificationTemplatePatchSchema,
  PORTAL_NOTIFICATION_CATALOG,
} from "../notifications";

const ALL_CODES = [
  "password_reset",
  "maker_checker_pending",
  "maker_checker_approved",
  "maker_checker_rejected",
  "invoice_issued",
  "invoice_overdue",
  "subscription_suspended",
  "system_announcement",
  "member_activated",
  "kyc_submission_approved",
  "kyc_submission_rejected",
  "loan_application_approved",
  "loan_application_rejected",
];

describe("PORTAL_NOTIFICATION_CATALOG", () => {
  it("mirrors the backend catalog's 13 codes with valid rows", () => {
    expect(PORTAL_NOTIFICATION_CATALOG.map((r) => r.code)).toEqual(ALL_CODES);
    for (const row of PORTAL_NOTIFICATION_CATALOG) {
      expect(row.label.length).toBeGreaterThan(0);
      expect(row.audiences.length).toBeGreaterThan(0);
      for (const a of row.audiences) {
        expect(["platform", "tenant", "member"]).toContain(a);
      }
      for (const c of row.channels) {
        expect(["email", "in_app"]).toContain(c);
      }
    }
  });

  it("catalogForAudience returns the member-visible codes", () => {
    expect(catalogForAudience("member").map((r) => r.code)).toEqual([
      "password_reset",
      "system_announcement",
      "member_activated",
      "kyc_submission_approved",
      "kyc_submission_rejected",
      "loan_application_approved",
      "loan_application_rejected",
    ]);
  });
});

describe("notificationTemplatePatchSchema", () => {
  it("accepts partial bodies", () => {
    expect(
      notificationTemplatePatchSchema.safeParse({ body_text: "Hello" }).success,
    ).toBe(true);
    expect(notificationTemplatePatchSchema.safeParse({}).success).toBe(true);
  });

  it("rejects a non-boolean is_active", () => {
    expect(
      notificationTemplatePatchSchema.safeParse({ is_active: "yes" }).success,
    ).toBe(false);
  });
});
