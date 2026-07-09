// admin/packages/schemas/src/kyc.ts
import { z } from "zod";

// ---- Wire shapes (mirror app/modules/organization/schemas.py and
// app/platform_/kyc/schemas.py; dates are ISO strings over the wire). ----

export interface KycFieldStatusOut {
  key: string;
  label: string;
  required: boolean;
  present: boolean;
}

export interface KycCompletionOut {
  items: KycFieldStatusOut[];
  required_total: number;
  required_present: number;
  percent: number;
  missing_required: string[];
  is_complete: boolean;
}

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

// Mirrors OrganizationKycValuesIn: 13 catalog keys, each nullable. The form
// models "not provided" as "" and toOrganizationKycPayload converts back to
// null so a blank never gets stored as a present-looking empty string.
export const organizationKycFormSchema = z.object({
  legal_name: z.string().trim(),
  registration_number: z.string().trim(),
  registered_address: z.string().trim(),
  primary_contact_name: z.string().trim(),
  primary_contact_email: z
    .string()
    .trim()
    .toLowerCase()
    .email("Enter a valid email address")
    .or(z.literal("")),
  registration_date: z
    .string()
    .regex(ISO_DATE_RE, "Use the date picker (YYYY-MM-DD)")
    .or(z.literal("")),
  regulator_name: z.string().trim(),
  license_number: z.string().trim(),
  tax_id: z.string().trim(),
  primary_contact_phone: z.string().trim(),
  postal_address: z.string().trim(),
  district_region: z.string().trim(),
  country: z.string().trim(),
});
export type OrganizationKycFormInput = z.infer<typeof organizationKycFormSchema>;
export type OrganizationKycFieldKey = keyof OrganizationKycFormInput;

export type OrganizationKycValuesOut = { [K in OrganizationKycFieldKey]: string | null };
export type OrganizationKycValuesIn = { [K in OrganizationKycFieldKey]: string | null };

export interface OrganizationKycOut {
  values: OrganizationKycValuesOut;
  verified: boolean;
  verified_at: string | null;
  verified_by_platform_user_id: string | null;
  completion: KycCompletionOut;
}

export interface SaccoKycRequirementItemOut {
  key: string;
  label: string;
  locked: boolean;
  required: boolean;
}

export interface SaccoKycRequirementsOut {
  items: SaccoKycRequirementItemOut[];
}

// ---- Form-rendering config. Labels mirror SACCO_KYC_CATALOG in
// app/core/kyc/catalog.py verbatim. `required` is NOT here — it is
// config-dependent and read at runtime from completion.items. ----

export interface OrganizationKycFieldSpec {
  key: OrganizationKycFieldKey;
  label: string;
  kind: "text" | "email" | "date";
  locked: boolean;
}

export const ORGANIZATION_KYC_FIELDS: readonly OrganizationKycFieldSpec[] = [
  { key: "legal_name", label: "Registered legal name", kind: "text", locked: true },
  { key: "registration_number", label: "Registration number", kind: "text", locked: true },
  { key: "registered_address", label: "Registered physical address", kind: "text", locked: true },
  { key: "primary_contact_name", label: "Primary contact name", kind: "text", locked: true },
  { key: "primary_contact_email", label: "Primary contact email", kind: "email", locked: true },
  { key: "registration_date", label: "Date of registration", kind: "date", locked: false },
  { key: "regulator_name", label: "Regulator", kind: "text", locked: false },
  { key: "license_number", label: "License number", kind: "text", locked: false },
  { key: "tax_id", label: "Tax identification number", kind: "text", locked: false },
  { key: "primary_contact_phone", label: "Primary contact phone", kind: "text", locked: false },
  { key: "postal_address", label: "Postal address", kind: "text", locked: false },
  { key: "district_region", label: "District / region", kind: "text", locked: false },
  { key: "country", label: "Country", kind: "text", locked: false },
];

/** Server nulls → form empty strings. */
export function organizationKycFormDefaults(
  values: OrganizationKycValuesOut,
): OrganizationKycFormInput {
  const out = {} as Record<OrganizationKycFieldKey, string>;
  for (const field of ORGANIZATION_KYC_FIELDS) {
    out[field.key] = values[field.key] ?? "";
  }
  return out;
}

/** Form empty/blank strings → null on the wire. */
export function toOrganizationKycPayload(
  input: OrganizationKycFormInput,
): OrganizationKycValuesIn {
  const out = {} as Record<OrganizationKycFieldKey, string | null>;
  for (const field of ORGANIZATION_KYC_FIELDS) {
    const raw = input[field.key].trim();
    out[field.key] = raw === "" ? null : raw;
  }
  return out;
}

// ---- Member KYC (increment 4). Requirement items share the SACCO shape. ----

export type MemberKycRequirementsOut = SaccoKycRequirementsOut;

export interface MemberKycOut {
  member_id: string;
  completion: KycCompletionOut;
}

export interface MemberSelfKycOut {
  completion: KycCompletionOut;
}
