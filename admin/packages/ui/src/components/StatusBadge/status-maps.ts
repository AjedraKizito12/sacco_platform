// Per docs/sacco-design-system-v2.md §"Domain Status Mapping". Adding a
// new status means adding a row in the relevant map.

import type { BadgeProps } from "../Badge";

export type StatusEntity =
  | "loan"
  | "member"
  | "tenant"
  | "savings_account"
  | "fee_assessment"
  | "approval_request"
  | "subscription"
  | "subscription_plan"
  | "invoice"
  | "payment"
  | "platform_user"
  | "jwt_key"
  | "tenant_user"
  | "loan_application"
  | "guarantor";

interface MapEntry {
  variant: NonNullable<BadgeProps["variant"]>;
  label: string;
}

type StatusMap = Record<string, MapEntry>;

export const LOAN_STATUS: StatusMap = {
  draft: { variant: "neutral", label: "Draft" },
  submitted: { variant: "info", label: "Submitted" },
  under_review: { variant: "info", label: "Under Review" },
  approved: { variant: "success", label: "Approved" },
  disbursing: { variant: "warning", label: "Disbursing" },
  disbursed: { variant: "success", label: "Disbursed" },
  in_arrears: { variant: "danger-solid", label: "In Arrears" },
  restructured: { variant: "accent", label: "Restructured" },
  written_off: { variant: "danger", label: "Written Off" },
  closed: { variant: "dark", label: "Closed" },
  rejected: { variant: "danger", label: "Rejected" },
  withdrawn: { variant: "neutral", label: "Withdrawn" },
  cancelled: { variant: "neutral", label: "Cancelled" },
};

export const MEMBER_STATUS: StatusMap = {
  prospect: { variant: "info", label: "Prospect" },
  active: { variant: "success", label: "Active" },
  dormant: { variant: "warning", label: "Dormant" },
  suspended: { variant: "danger-solid", label: "Suspended" },
  exited: { variant: "neutral", label: "Exited" },
  deceased: { variant: "dark", label: "Deceased" },
};

export const TENANT_STATUS: StatusMap = {
  pending: { variant: "info", label: "Pending" },
  provisioning: { variant: "warning", label: "Provisioning" },
  active: { variant: "success", label: "Active" },
  suspended: { variant: "danger-solid", label: "Suspended" },
  failed: { variant: "danger", label: "Failed" },
  deprovisioning: { variant: "warning", label: "Deprovisioning" },
  archived: { variant: "neutral", label: "Archived" },
};

export const SAVINGS_ACCOUNT_STATUS: StatusMap = {
  active: { variant: "success", label: "Active" },
  dormant: { variant: "warning", label: "Dormant" },
  frozen: { variant: "danger-solid", label: "Frozen" },
  closed: { variant: "neutral", label: "Closed" },
};

export const FEE_ASSESSMENT_STATUS: StatusMap = {
  assessed: { variant: "warning", label: "Assessed" },
  partially_paid: { variant: "info", label: "Partially Paid" },
  paid: { variant: "success", label: "Paid" },
  waived: { variant: "accent", label: "Waived" },
  cancelled: { variant: "neutral", label: "Cancelled" },
};

export const APPROVAL_REQUEST_STATUS: StatusMap = {
  pending: { variant: "warning", label: "Pending Approval" },
  approved: { variant: "info", label: "Approved" },
  rejected: { variant: "danger", label: "Rejected" },
  executed: { variant: "success", label: "Executed" },
  execution_failed: { variant: "danger-solid", label: "Execution Failed" },
  expired: { variant: "neutral", label: "Expired" },
  cancelled: { variant: "neutral", label: "Cancelled" },
};

export const SUBSCRIPTION_PLAN_STATUS: StatusMap = {
  active: { variant: "success", label: "Active" },
  inactive: { variant: "neutral", label: "Inactive" },
};

export const SUBSCRIPTION_STATUS: StatusMap = {
  pending: { variant: "info", label: "Pending" },
  trialing: { variant: "info", label: "Trialing" },
  active: { variant: "success", label: "Active" },
  past_due: { variant: "warning", label: "Past due" },
  suspended: { variant: "danger-solid", label: "Suspended" },
  cancelled: { variant: "neutral", label: "Cancelled" },
};

export const INVOICE_STATUS: StatusMap = {
  draft: { variant: "neutral", label: "Draft" },
  issued: { variant: "info", label: "Issued" },
  partial: { variant: "warning", label: "Partial" },
  paid: { variant: "success", label: "Paid" },
  overdue: { variant: "danger-solid", label: "Overdue" },
  void: { variant: "neutral", label: "Void" },
};

export const PAYMENT_STATUS: StatusMap = {
  pending: { variant: "warning", label: "Pending Confirmation" },
  confirmed: { variant: "success", label: "Confirmed" },
  rejected: { variant: "danger", label: "Rejected" },
};

export const PLATFORM_USER_STATUS: StatusMap = {
  active: { variant: "success", label: "Active" },
  inactive: { variant: "neutral", label: "Inactive" },
};

export const JWT_KEY_STATUS: StatusMap = {
  active: { variant: "success", label: "Active" },
  retiring: { variant: "warning", label: "Retiring" },
  retired: { variant: "neutral", label: "Retired" },
};

export const TENANT_USER_STATUS: StatusMap = {
  active: { variant: "success", label: "Active" },
  inactive: { variant: "neutral", label: "Inactive" },
};

export const LOAN_APPLICATION_STATUS: StatusMap = {
  pending: { variant: "info", label: "Pending" },
  approved: { variant: "success", label: "Approved" },
  rejected: { variant: "danger", label: "Rejected" },
  withdrawn: { variant: "neutral", label: "Withdrawn" },
  cancelled: { variant: "neutral", label: "Cancelled" },
};

export const GUARANTOR_STATUS: StatusMap = {
  pending: { variant: "info", label: "Pending" },
  accepted: { variant: "success", label: "Accepted" },
  declined: { variant: "danger", label: "Declined" },
  released: { variant: "neutral", label: "Released" },
};

const ENTITY_MAPS: Record<StatusEntity, StatusMap> = {
  loan: LOAN_STATUS,
  member: MEMBER_STATUS,
  tenant: TENANT_STATUS,
  savings_account: SAVINGS_ACCOUNT_STATUS,
  fee_assessment: FEE_ASSESSMENT_STATUS,
  approval_request: APPROVAL_REQUEST_STATUS,
  subscription: SUBSCRIPTION_STATUS,
  subscription_plan: SUBSCRIPTION_PLAN_STATUS,
  invoice: INVOICE_STATUS,
  payment: PAYMENT_STATUS,
  platform_user: PLATFORM_USER_STATUS,
  jwt_key: JWT_KEY_STATUS,
  tenant_user: TENANT_USER_STATUS,
  loan_application: LOAN_APPLICATION_STATUS,
  guarantor: GUARANTOR_STATUS,
};

export function resolveStatus(
  entity: StatusEntity,
  status: string,
): MapEntry | null {
  return ENTITY_MAPS[entity][status] ?? null;
}
