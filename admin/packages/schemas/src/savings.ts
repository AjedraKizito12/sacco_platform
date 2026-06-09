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
