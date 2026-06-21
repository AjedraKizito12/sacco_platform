// admin/packages/schemas/src/savings.ts
import { z } from "zod";
import { idempotencyKey, moneyString, uuid } from "./common";

export const openAccountSchema = z.object({
  member_id: uuid,
  savings_product_id: uuid,
});

const baseTransactionSchema = z.object({
  amount: moneyString({ min: "0.01" }),
  payment_account_id: uuid,
  idempotency_key: idempotencyKey,
  narration: z.string().trim().max(280).optional().or(z.literal("")),
});

export const depositSchema = baseTransactionSchema;
export const withdrawSchema = baseTransactionSchema;

export const savingsProductSchema = z.object({
  name: z.string().trim().min(1).max(200),
  interest_rate: moneyString({ min: "0", max: "100" }),
  liability_account_id: uuid,
  minimum_balance: moneyString({ min: "0" }),
});

export type OpenAccountInput = z.infer<typeof openAccountSchema>;
export type DepositInput = z.infer<typeof depositSchema>;
export type WithdrawInput = z.infer<typeof withdrawSchema>;
export type SavingsProductInput = z.infer<typeof savingsProductSchema>;

// Mirror app/modules/savings/schemas.py. Decimals are JSON strings.
export interface SavingsProductOut {
  id: string;
  name: string;
  interest_rate: string;
  minimum_balance: string;
  liability_account_id: string;
  is_active: boolean;
}

export interface SavingsAccountOut {
  id: string;
  member_id: string;
  savings_product_id: string;
  product_name: string;
  interest_rate: string;
  minimum_balance: string;
  liability_account_id: string;
}

export interface SavingsAccountWithBalanceOut extends SavingsAccountOut {
  balance: string;
}

export interface SavingsTransactionOut {
  id: string;
  savings_account_id: string;
  transaction_type: string;
  amount: string;
  narration: string | null;
  journal_entry_id: string;
  posted_by: string;
}
