// admin/packages/schemas/src/ledger.ts
import { z } from "zod";
import { idempotencyKey, moneyString, uuid } from "./common";

export const accountTypeSchema = z.enum([
  "asset",
  "liability",
  "equity",
  "income",
  "expense",
]);

export const accountSchema = z.object({
  code: z
    .string()
    .trim()
    .min(1)
    .max(20)
    .regex(/^[A-Z0-9.\-_]+$/, "Use uppercase letters, digits, ., -, or _"),
  name: z.string().trim().min(1).max(200),
  account_type: accountTypeSchema,
  parent_id: uuid.optional(),
  description: z.string().trim().max(1000).optional().or(z.literal("")),
});

// Manual GL entry — debits MUST equal credits.
export const journalLineSchema = z.object({
  account_id: uuid,
  debit_amount: moneyString({ min: "0" }).default("0"),
  credit_amount: moneyString({ min: "0" }).default("0"),
  description: z.string().trim().max(500).optional().or(z.literal("")),
});

export const manualJournalEntrySchema = z
  .object({
    reference: z.string().trim().min(1).max(50),
    description: z.string().trim().min(1).max(500),
    lines: z.array(journalLineSchema).min(2, "Need at least two lines"),
    idempotency_key: idempotencyKey,
  })
  .refine(
    (data) => {
      const totalDebit = data.lines.reduce(
        (s, l) => s + Number.parseFloat(l.debit_amount),
        0,
      );
      const totalCredit = data.lines.reduce(
        (s, l) => s + Number.parseFloat(l.credit_amount),
        0,
      );
      return Math.abs(totalDebit - totalCredit) < 0.0001;
    },
    { message: "Debits must equal credits", path: ["lines"] },
  )
  .refine(
    (data) =>
      data.lines.every(
        (l) =>
          (Number.parseFloat(l.debit_amount) > 0) !==
          (Number.parseFloat(l.credit_amount) > 0),
      ),
    {
      message: "Each line must be either a debit OR a credit, not both",
      path: ["lines"],
    },
  );

export type AccountInput = z.infer<typeof accountSchema>;
export type ManualJournalEntryInput = z.infer<typeof manualJournalEntrySchema>;
export type AccountType = z.infer<typeof accountTypeSchema>;

// Mirror app/modules/ledger/schemas.py. Decimals are JSON strings.
export interface AccountOut {
  id: string;
  code: string;
  name: string;
  account_type: string;
  parent_id: string | null;
  is_active: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface AccountWithBalanceOut extends AccountOut {
  balance: string;
}

export interface JournalLineOut {
  id: string;
  account_id: string;
  debit_amount: string;
  credit_amount: string;
  description: string | null;
}

export interface JournalEntryOut {
  id: string;
  reference: string;
  description: string;
  posted_by: string;
  posted_at: string;
  idempotency_key: string;
  lines: JournalLineOut[];
}

export interface ManualGLSubmitOut {
  approval_request_id: string;
  status: string;
}
