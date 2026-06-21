// admin/packages/schemas/src/shares.ts
import { z } from "zod";
import { idempotencyKey, intString, moneyString, uuid } from "./common";

export const openShareAccountSchema = z.object({
  member_id: uuid,
  share_product_id: uuid,
});

export const purchaseSharesSchema = z.object({
  quantity: intString({ min: 1 }),
  payment_account_id: uuid,
  idempotency_key: idempotencyKey,
});

export const redeemSharesSchema = z.object({
  quantity: intString({ min: 1 }),
  payment_account_id: uuid,
  reason: z.string().trim().max(280).optional().or(z.literal("")),
  idempotency_key: idempotencyKey,
});

export const shareProductSchema = z.object({
  name: z.string().trim().min(1).max(200),
  par_value: moneyString({ min: "0.01" }),
  minimum_shares: intString({ min: 1 }),
  maximum_shares: intString({ min: 1 }).optional().or(z.literal("")),
  share_capital_account_id: uuid,
});

export type OpenShareAccountInput = z.infer<typeof openShareAccountSchema>;
export type PurchaseSharesInput = z.infer<typeof purchaseSharesSchema>;
export type RedeemSharesInput = z.infer<typeof redeemSharesSchema>;
export type ShareProductInput = z.infer<typeof shareProductSchema>;

// Mirror app/modules/shares/schemas.py. Decimals are JSON strings; counts are numbers.
export interface ShareProductOut {
  id: string;
  name: string;
  par_value: string;
  minimum_shares: number;
  maximum_shares: number | null;
  share_capital_account_id: string;
  is_active: boolean;
}

export interface ShareAccountOut {
  id: string;
  member_id: string;
  share_product_id: string;
}

export interface ShareAccountWithBalanceOut extends ShareAccountOut {
  shares_held: number;
  total_value: string;
}

export interface ShareTransactionOut {
  id: string;
  share_account_id: string;
  transaction_type: string;
  quantity: number;
  amount: string;
  journal_entry_id: string;
  posted_by: string;
}

export interface ShareAccountListItemOut {
  id: string;
  member_id: string;
  share_product_id: string;
  product_name: string;
  par_value: string;
  shares_held: number;
  total_value: string;
}
