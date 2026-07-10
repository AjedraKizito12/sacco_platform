// admin/packages/schemas/src/member.ts
import { z } from "zod";
import { isoDate, uuid } from "./common";

export const memberGenderSchema = z.enum(["M", "F", "X"]);

export const idDocumentTypeSchema = z.enum([
  "national_id",
  "passport",
  "driving_license",
  "voters_card",
]);

export const memberRegistrationSchema = z.object({
  full_name: z.string().trim().min(1, "Full name is required").max(200),
  date_of_birth: isoDate,
  gender: memberGenderSchema,
  phone: z
    .string()
    .trim()
    .regex(/^\+?[0-9\s-]{7,20}$/, "Must be a valid phone number")
    .optional()
    .or(z.literal("")),
  email: z
    .string()
    .trim()
    .toLowerCase()
    .email("Must be a valid email")
    .optional()
    .or(z.literal("")),
  physical_address: z.string().trim().max(500).optional().or(z.literal("")),
  national_id_number: z.string().trim().max(50).optional().or(z.literal("")),
  id_document_type: idDocumentTypeSchema.optional(),
  id_document_number: z.string().trim().max(50).optional().or(z.literal("")),
  id_issued_date: isoDate.optional(),
  id_expiry_date: isoDate.optional(),
});

export const memberStatusSchema = z.enum([
  "prospect",
  "active",
  "dormant",
  "suspended",
  "exited",
  "deceased",
]);

export const memberStatusChangeSchema = z.object({
  new_status: memberStatusSchema,
  reason: z
    .string()
    .trim()
    .min(10, "Reason must be at least 10 characters")
    .max(500),
  idempotency_key: z.string().min(8),
});

// Tenant id (UUID) helper used by other forms that target a specific member.
export const memberIdSchema = uuid;

// Mirrors app/modules/members/schemas.py MemberOut. Dates are ISO strings.
export interface MemberOut {
  id: string;
  member_number: string;
  full_name: string;
  date_of_birth: string;
  gender: string;
  phone: string | null;
  email: string | null;
  physical_address: string | null;
  national_id_number: string | null;
  id_document_type: string | null;
  id_document_number: string | null;
  id_issued_date: string | null;
  id_expiry_date: string | null;
  status: string;
  joined_at: string | null;
  created_at: string;
  updated_at: string;
}

export type MemberRegistrationInput = z.infer<typeof memberRegistrationSchema>;
export type MemberStatusChangeInput = z.infer<typeof memberStatusChangeSchema>;
export type MemberStatus = z.infer<typeof memberStatusSchema>;
export type MemberGender = z.infer<typeof memberGenderSchema>;
export type IdDocumentType = z.infer<typeof idDocumentTypeSchema>;

// Consolidated statement date range (both ends optional).
const optionalStatementDate = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/, "Use YYYY-MM-DD")
  .or(z.literal(""));

export const memberStatementRangeSchema = z
  .object({
    from_date: optionalStatementDate,
    to_date: optionalStatementDate,
  })
  .refine((v) => !v.from_date || !v.to_date || v.from_date <= v.to_date, {
    message: "The start date must be before the end date",
    path: ["to_date"],
  });

export type MemberStatementRangeInput = z.infer<typeof memberStatementRangeSchema>;
