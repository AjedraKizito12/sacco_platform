import { describe, expect, it } from "vitest";
import {
  ORGANIZATION_KYC_FIELDS,
  organizationKycFormDefaults,
  organizationKycFormSchema,
  toOrganizationKycPayload,
  type OrganizationKycValuesOut,
} from "../kyc";

const serverValues: OrganizationKycValuesOut = {
  legal_name: "Kampala Teachers SACCO",
  registration_number: null,
  registered_address: null,
  primary_contact_name: null,
  primary_contact_email: null,
  registration_date: null,
  regulator_name: null,
  license_number: null,
  tax_id: null,
  primary_contact_phone: null,
  postal_address: null,
  district_region: null,
  country: null,
};

describe("organizationKycFormSchema", () => {
  it("accepts a fully blank form (all fields optional client-side)", () => {
    const result = organizationKycFormSchema.safeParse(
      organizationKycFormDefaults(serverValues),
    );
    expect(result.success).toBe(true);
  });

  it("rejects a malformed contact email but accepts empty string", () => {
    const base = organizationKycFormDefaults(serverValues);
    expect(
      organizationKycFormSchema.safeParse({ ...base, primary_contact_email: "not-an-email" })
        .success,
    ).toBe(false);
    expect(
      organizationKycFormSchema.safeParse({ ...base, primary_contact_email: "" }).success,
    ).toBe(true);
  });

  it("rejects a malformed registration date but accepts empty string", () => {
    const base = organizationKycFormDefaults(serverValues);
    expect(
      organizationKycFormSchema.safeParse({ ...base, registration_date: "01/02/2026" }).success,
    ).toBe(false);
    expect(
      organizationKycFormSchema.safeParse({ ...base, registration_date: "2026-02-01" }).success,
    ).toBe(true);
  });
});

describe("organizationKycFormDefaults / toOrganizationKycPayload", () => {
  it("maps server nulls to empty strings for the form", () => {
    const defaults = organizationKycFormDefaults(serverValues);
    expect(defaults.legal_name).toBe("Kampala Teachers SACCO");
    expect(defaults.country).toBe("");
  });

  it("maps blank strings back to null on the wire (blank must not count as present)", () => {
    const payload = toOrganizationKycPayload({
      ...organizationKycFormDefaults(serverValues),
      country: "  ",
    });
    expect(payload.legal_name).toBe("Kampala Teachers SACCO");
    expect(payload.country).toBeNull();
    expect(payload.tax_id).toBeNull();
  });
});

describe("ORGANIZATION_KYC_FIELDS", () => {
  it("covers all 13 catalog keys with the 5 locked minimums first", () => {
    expect(ORGANIZATION_KYC_FIELDS).toHaveLength(13);
    expect(ORGANIZATION_KYC_FIELDS.filter((f) => f.locked).map((f) => f.key)).toEqual([
      "legal_name",
      "registration_number",
      "registered_address",
      "primary_contact_name",
      "primary_contact_email",
    ]);
  });
});

import {
  MEMBER_KYC_FIELDS,
  memberKycFormDefaults,
  memberKycFormSchema,
  toMemberKycPayload,
  type MemberKycValues,
} from "../kyc";

const EMPTY_VALUES: MemberKycValues = {
  phone: null,
  email: null,
  physical_address: null,
  national_id_number: null,
  id_document_type: null,
  id_document_number: null,
  id_issued_date: null,
  id_expiry_date: null,
  next_of_kin_name: null,
  next_of_kin_phone: null,
  occupation: null,
};

describe("member KYC form helpers", () => {
  it("has one field spec per editable catalog key", () => {
    expect(MEMBER_KYC_FIELDS.map((f) => f.key)).toEqual([
      "phone",
      "email",
      "physical_address",
      "national_id_number",
      "id_document_type",
      "id_document_number",
      "id_issued_date",
      "id_expiry_date",
      "next_of_kin_name",
      "next_of_kin_phone",
      "occupation",
    ]);
  });

  it("round-trips server nulls -> form blanks -> payload nulls", () => {
    const defaults = memberKycFormDefaults(EMPTY_VALUES);
    expect(defaults.phone).toBe("");
    const payload = toMemberKycPayload(defaults);
    expect(payload).toEqual(EMPTY_VALUES);
  });

  it("keeps provided values through the round trip", () => {
    const defaults = memberKycFormDefaults({
      ...EMPTY_VALUES,
      phone: "+256700000001",
      id_document_type: "passport",
    });
    const payload = toMemberKycPayload(defaults);
    expect(payload.phone).toBe("+256700000001");
    expect(payload.id_document_type).toBe("passport");
  });

  it("rejects a malformed date but accepts blank", () => {
    const base = memberKycFormDefaults(EMPTY_VALUES);
    expect(
      memberKycFormSchema.safeParse({ ...base, id_issued_date: "01/02/2020" }).success,
    ).toBe(false);
    expect(
      memberKycFormSchema.safeParse({ ...base, id_issued_date: "" }).success,
    ).toBe(true);
  });
});
